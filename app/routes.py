"""HTTP routes: login, dashboard, tickets, status updates, attachments, health."""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from .models import CATEGORIES, PRIORITIES, STATUSES, TRANSITIONS, Attachment, Ticket, TicketHistory, User
from .security import new_csrf_token, tokens_match, verify_password
from .storage import ALLOWED_EXTENSIONS, build_key, extension_of

log = logging.getLogger("ticketdesk")
router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ---------------------------------------------------------------- helpers

class LoginRequired(Exception):
    """Raised by `current_user`; turned into a redirect to /login."""


def get_db(request: Request):
    db: Session = request.app.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        request.session.clear()
        raise LoginRequired()
    return user


def require_staff(user: User = Depends(current_user)) -> User:
    if not user.is_staff:
        raise HTTPException(status_code=403, detail="Only support staff can do this.")
    return user


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = new_csrf_token()
        request.session["csrf"] = token
    return token


async def verify_csrf(request: Request) -> None:
    form = await request.form()
    if not tokens_match(form.get("csrf_token"), request.session.get("csrf")):
        raise HTTPException(status_code=400, detail="Form expired. Go back, reload the page and try again.")


def flash(request: Request, message: str, kind: str = "info") -> None:
    flashes = request.session.get("flashes", [])
    flashes.append([kind, message])
    request.session["flashes"] = flashes


def render(request: Request, name: str, ctx: dict | None = None, user: User | None = None, status_code: int = 200):
    context = dict(ctx or {})
    context.update(user=user, csrf_token=csrf_token(request), flashes=request.session.pop("flashes", []))
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def visible_tickets(user: User):
    """Staff see every ticket; regular users see only their own."""
    stmt = select(Ticket)
    if not user.is_staff:
        stmt = stmt.where(Ticket.created_by == user.id)
    return stmt


def load_ticket(db: Session, ticket_id: int, user: User) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or (not user.is_staff and ticket.created_by != user.id):
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


# ---------------------------------------------------------------- auth

@router.get("/")
def index(request: Request):
    return redirect("/dashboard" if request.session.get("uid") else "/login")


@router.get("/login")
def login_form(request: Request):
    if request.session.get("uid"):
        return redirect("/dashboard")
    return render(request, "login.html")


@router.post("/login", dependencies=[Depends(verify_csrf)])
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        log.warning("Failed login for username=%r from %s", username, request.client.host if request.client else "-")
        return render(request, "login.html", {"error": "Invalid username or password.", "username": username},
                      status_code=401)
    request.session.clear()
    request.session["uid"] = user.id
    request.session["csrf"] = new_csrf_token()
    log.info("User %s logged in", user.username)
    return redirect("/dashboard")


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


# ---------------------------------------------------------------- dashboard

@router.get("/dashboard")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    scope = visible_tickets(user).subquery()
    by_status = dict(db.execute(select(scope.c.status, func.count()).group_by(scope.c.status)).all())
    by_priority = dict(
        db.execute(
            select(scope.c.priority, func.count())
            .where(scope.c.status.in_(["Open", "In Progress"]))
            .group_by(scope.c.priority)
        ).all()
    )
    recent = db.scalars(visible_tickets(user).order_by(Ticket.updated_at.desc()).limit(8)).all()
    return render(
        request,
        "dashboard.html",
        {
            "status_counts": [(s, by_status.get(s, 0)) for s in STATUSES],
            "priority_counts": [(p, by_priority.get(p, 0)) for p in PRIORITIES],
            "total": sum(by_status.values()),
            "recent": recent,
        },
        user=user,
    )


# ---------------------------------------------------------------- tickets

@router.get("/tickets")
def list_tickets(
    request: Request,
    status: str = "",
    q: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = visible_tickets(user)
    if status in STATUSES:
        stmt = stmt.where(Ticket.status == status)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Ticket.title.ilike(like), Ticket.description.ilike(like)))
    tickets = db.scalars(stmt.order_by(Ticket.updated_at.desc())).all()
    return render(request, "tickets.html", {"tickets": tickets, "statuses": STATUSES, "status": status, "q": q},
                  user=user)


@router.get("/tickets/new")
def new_ticket_form(request: Request, user: User = Depends(current_user)):
    return render(request, "ticket_new.html", {"priorities": PRIORITIES, "categories": CATEGORIES, "form": {}},
                  user=user)


@router.post("/tickets", dependencies=[Depends(verify_csrf)])
def create_ticket(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    category: str = Form("Other"),
    priority: str = Form("Medium"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    title, description = title.strip(), description.strip()
    errors = []
    if not 3 <= len(title) <= 200:
        errors.append("Title must be between 3 and 200 characters.")
    if not description:
        errors.append("Please describe the problem.")
    if priority not in PRIORITIES:
        errors.append("Choose a valid priority.")
    if category not in CATEGORIES:
        errors.append("Choose a valid category.")
    if errors:
        form = {"title": title, "description": description, "category": category, "priority": priority}
        return render(request, "ticket_new.html",
                      {"errors": errors, "priorities": PRIORITIES, "categories": CATEGORIES, "form": form},
                      user=user, status_code=422)

    ticket = Ticket(title=title, description=description, category=category, priority=priority,
                    status="Open", created_by=user.id)
    db.add(ticket)
    db.flush()
    db.add(TicketHistory(ticket_id=ticket.id, from_status=None, to_status="Open", changed_by=user.id,
                         note="Ticket created"))
    db.commit()
    log.info("Ticket #%s created by %s", ticket.id, user.username)
    flash(request, f"Ticket #{ticket.id} created.", "success")
    return redirect(f"/tickets/{ticket.id}")


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: int, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    ticket = load_ticket(db, ticket_id, user)
    storage = request.app.state.storage
    attachments = [(a, storage.processing_status(a.storage_key)) for a in ticket.attachments]
    staff = db.scalars(select(User).where(User.role.in_(["agent", "admin"]), User.is_active).order_by(User.username)).all()
    return render(
        request,
        "ticket_detail.html",
        {
            "ticket": ticket,
            "attachments": attachments,
            "next_statuses": TRANSITIONS.get(ticket.status, []),
            "staff": staff,
            "allowed_ext": ", ".join(sorted(ALLOWED_EXTENSIONS)),
            "max_mb": request.app.state.settings.max_upload_mb,
        },
        user=user,
    )


@router.post("/tickets/{ticket_id}/status", dependencies=[Depends(verify_csrf)])
def update_status(
    ticket_id: int,
    request: Request,
    new_status: str = Form(...),
    note: str = Form(""),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    ticket = load_ticket(db, ticket_id, user)
    if new_status not in TRANSITIONS.get(ticket.status, []):
        flash(request, f"Can't move a ticket from {ticket.status} to {new_status}.", "error")
        return redirect(f"/tickets/{ticket.id}")
    old = ticket.status
    ticket.status = new_status
    if new_status == "In Progress" and ticket.assigned_to is None:
        ticket.assigned_to = user.id
    db.add(TicketHistory(ticket_id=ticket.id, from_status=old, to_status=new_status, changed_by=user.id,
                         note=note.strip()[:2000]))
    db.commit()
    log.info("Ticket #%s: %s -> %s by %s", ticket.id, old, new_status, user.username)
    flash(request, f"Status changed to {new_status}.", "success")
    return redirect(f"/tickets/{ticket.id}")


@router.post("/tickets/{ticket_id}/assign", dependencies=[Depends(verify_csrf)])
def assign_ticket(
    ticket_id: int,
    request: Request,
    assignee_id: str = Form(""),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    ticket = load_ticket(db, ticket_id, user)
    if assignee_id:
        assignee = db.get(User, int(assignee_id))
        if assignee is None or not assignee.is_staff:
            flash(request, "Tickets can only be assigned to support staff.", "error")
            return redirect(f"/tickets/{ticket.id}")
        ticket.assigned_to = assignee.id
    else:
        ticket.assigned_to = None
    db.commit()
    flash(request, "Assignment updated.", "success")
    return redirect(f"/tickets/{ticket.id}")


# ---------------------------------------------------------------- attachments

@router.post("/tickets/{ticket_id}/attachments", dependencies=[Depends(verify_csrf)])
def upload_attachment(
    ticket_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ticket = load_ticket(db, ticket_id, user)
    settings = request.app.state.settings
    back = redirect(f"/tickets/{ticket.id}")

    if ticket.status == "Closed":
        flash(request, "Closed tickets can't take new attachments.", "error")
        return back
    name = file.filename or ""
    if extension_of(name) not in ALLOWED_EXTENSIONS:
        flash(request, f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.", "error")
        return back
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size == 0:
        flash(request, "That file is empty.", "error")
        return back
    if size > settings.max_upload_bytes:
        flash(request, f"File is larger than {settings.max_upload_mb} MB.", "error")
        return back

    content_type = file.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    key = build_key(settings.s3_prefix, ticket.id, name)
    try:
        request.app.state.storage.save(key, file.file, content_type)
    except Exception:
        log.exception("Attachment upload failed for ticket #%s", ticket.id)
        flash(request, "Upload failed. Check the application logs.", "error")
        return back

    db.add(Attachment(ticket_id=ticket.id, original_name=name[:255], storage_key=key, content_type=content_type,
                      size_bytes=size, uploaded_by=user.id))
    db.commit()
    log.info("Attachment %s (%d bytes) added to ticket #%s by %s", key, size, ticket.id, user.username)
    flash(request, f"Uploaded {name}.", "success")
    return back


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, request: Request, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    load_ticket(db, attachment.ticket_id, user)  # permission check
    return request.app.state.storage.download_response(
        attachment.storage_key, attachment.original_name, attachment.content_type
    )


# ---------------------------------------------------------------- health

@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        log.error("Health check: database unreachable: %s", exc)
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return {"status": "ok", "database": "ok", "storage": request.app.state.storage.backend}
