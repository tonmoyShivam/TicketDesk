from app.models import TRANSITIONS


def test_login_success_and_failure(browser):
    b = browser()
    assert b.login("ravi", "wrong").status_code == 401
    resp = b.login("ravi")
    assert resp.status_code == 200 and "Dashboard" in resp.text


def test_pages_require_login(browser):
    b = browser()
    for url in ["/dashboard", "/tickets", "/tickets/new", "/tickets/1"]:
        resp = b.get(url, follow_redirects=False)
        assert resp.status_code == 303 and resp.headers["location"] == "/login"


def test_post_without_csrf_is_rejected(browser):
    b = browser()
    b.login("ravi")
    resp = b.client.post("/tickets", data={"title": "x" * 10, "description": "y"})
    assert resp.status_code == 400


def test_create_ticket_and_validation(browser):
    b = browser()
    b.login("ravi")
    tid = b.new_ticket("Printer jammed")
    page = b.get(f"/tickets/{tid}")
    assert "Printer jammed" in page.text and "Open" in page.text
    bad = b.post("/tickets", {"title": "x", "description": "", "category": "Other", "priority": "Medium"})
    assert bad.status_code == 422 and "Title must be" in bad.text


def test_status_workflow_for_staff(browser):
    user, agent = browser(), browser()
    user.login("ravi")
    tid = user.new_ticket()
    agent.login("agent")
    for status in ["In Progress", "Resolved", "Closed"]:
        resp = agent.post(f"/tickets/{tid}/status", {"new_status": status})
        assert f"Status changed to {status}" in resp.text
    # Closed is final
    resp = agent.post(f"/tickets/{tid}/status", {"new_status": "Open"})
    assert "Can&#39;t move" in resp.text or "Can't move" in resp.text
    assert TRANSITIONS["Closed"] == []


def test_illegal_transition_rejected(browser):
    agent = browser()
    agent.login("agent")
    tid = agent.new_ticket()
    resp = agent.post(f"/tickets/{tid}/status", {"new_status": "Closed"})
    assert "Can" in resp.text and "move a ticket from Open to Closed" in resp.text


def test_regular_user_cannot_change_status(browser):
    b = browser()
    b.login("ravi")
    tid = b.new_ticket()
    assert b.post(f"/tickets/{tid}/status", {"new_status": "In Progress"}).status_code == 403


def test_users_only_see_own_tickets(browser):
    ravi, meena, agent = browser(), browser(), browser()
    ravi.login("ravi")
    meena.login("meena")
    agent.login("agent")
    tid = ravi.new_ticket("Ravi's private issue")
    assert meena.get(f"/tickets/{tid}").status_code == 404
    assert "Ravi&#39;s private issue" not in meena.get("/tickets").text
    assert agent.get(f"/tickets/{tid}").status_code == 200


def test_dashboard_counts(browser):
    agent = browser()
    agent.login("agent")
    for _ in range(3):
        agent.new_ticket()
    tid = agent.new_ticket()
    agent.post(f"/tickets/{tid}/status", {"new_status": "In Progress"})
    html = agent.get("/dashboard").text
    assert "4 in total" in html


def test_attachment_upload_and_download(browser):
    b = browser()
    b.login("ravi")
    tid = b.new_ticket()
    resp = b.post(f"/tickets/{tid}/attachments", files={"file": ("error.txt", b"stack trace here", "text/plain")})
    assert "Uploaded error.txt" in resp.text
    download = b.get("/attachments/1")
    assert download.status_code == 200 and download.content == b"stack trace here"


def test_attachment_rules(browser):
    b = browser()
    b.login("ravi")
    tid = b.new_ticket()
    resp = b.post(f"/tickets/{tid}/attachments", files={"file": ("run.exe", b"MZ", "application/octet-stream")})
    assert "File type not allowed" in resp.text
    resp = b.post(f"/tickets/{tid}/attachments", files={"file": ("empty.txt", b"", "text/plain")})
    assert "empty" in resp.text
    big = b"x" * (10 * 1024 * 1024 + 1)
    resp = b.post(f"/tickets/{tid}/attachments", files={"file": ("big.log", big, "text/plain")})
    assert "larger than 10 MB" in resp.text


def test_other_users_cannot_download(browser):
    ravi, meena = browser(), browser()
    ravi.login("ravi")
    meena.login("meena")
    tid = ravi.new_ticket()
    ravi.post(f"/tickets/{tid}/attachments", files={"file": ("a.txt", b"secret", "text/plain")})
    assert meena.get("/attachments/1").status_code == 404


def test_health(browser):
    assert browser().get("/health").json() == {"status": "ok", "database": "ok", "storage": "local"}
