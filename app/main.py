"""Application factory.

Run locally:   uvicorn app.main:create_app --factory --reload
On EC2:        systemd runs uvicorn behind nginx (see deploy/ec2/ticketdesk.service)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings
from .db import build_engine
from .routes import LoginRequired, router, templates
from .storage import build_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = build_engine(settings)

    app = FastAPI(title="TicketDesk", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.storage = build_storage(settings)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="td_session",
        same_site="lax",
        https_only=settings.https_only_cookies,
        max_age=8 * 3600,
    )
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    app.include_router(router)

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if "text/html" not in request.headers.get("accept", ""):
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        html = templates.get_template("error.html").render(status=exc.status_code, detail=exc.detail)
        return HTMLResponse(html, status_code=exc.status_code)

    logging.getLogger("ticketdesk").info(
        "TicketDesk started (database=%s, storage=%s)",
        "url" if settings.database_url else "rds+secretsmanager",
        settings.storage_backend,
    )
    return app
