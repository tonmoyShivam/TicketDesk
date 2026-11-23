import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "correct-horse-battery"
_HASH = hash_password(PASSWORD)  # hash once; PBKDF2 is deliberately slow


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=str(tmp_path / "uploads"),
        secret_key="x" * 64,
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    with Session(application.state.engine) as db:
        db.add_all([
            User(username="admin", full_name="Asha Admin", role="admin", password_hash=_HASH),
            User(username="agent", full_name="Arun Agent", role="agent", password_hash=_HASH),
            User(username="ravi", full_name="Ravi User", role="user", password_hash=_HASH),
            User(username="meena", full_name="Meena User", role="user", password_hash=_HASH),
        ])
        db.commit()
    return application


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no CSRF token on page"
    return match.group(1)


class Browser:
    def __init__(self, client: TestClient):
        self.client = client
        self.token = None

    def login(self, username, password=PASSWORD):
        page = self.client.get("/login")
        resp = self.client.post("/login", data={"username": username, "password": password,
                                                "csrf_token": csrf(page.text)})
        if resp.status_code == 200:
            self.token = csrf(resp.text)
        return resp

    def post(self, url, data=None, **kw):
        return self.client.post(url, data={**(data or {}), "csrf_token": self.token}, **kw)

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def new_ticket(self, title="Laptop won't boot", priority="High"):
        resp = self.post("/tickets", {"title": title, "description": "Black screen after update",
                                      "category": "Hardware", "priority": priority})
        assert resp.status_code == 200
        return int(str(resp.url).rstrip("/").split("/")[-1])


@pytest.fixture
def browser(app):
    return lambda: Browser(TestClient(app))
