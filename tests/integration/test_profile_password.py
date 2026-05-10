"""
Integration tests for the user-profile and password-change endpoints.

These run against a real FastAPI app instance via ``TestClient``, hitting
the live PostgreSQL configured by ``conftest.setup_test_database``. They
cover the *successful* update path, the *negative* paths that should
return 4xx, and the audit-log side effect of a password change.
"""

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.password_change import PasswordChange
from app.models.user import User

logger = logging.getLogger(__name__)


@pytest.fixture()
def client() -> TestClient:
    """Plain TestClient. Each request commits its own session via get_db()."""
    return TestClient(app)


def _register_and_login(client: TestClient, password: str = "OrigPass1!") -> dict:
    """
    Register a new throwaway user and return ``{user, token, password}``.

    Uses uuid4-suffixed usernames/emails so tests don't collide when run in
    parallel or repeated against the same database.
    """
    suffix = uuid4().hex[:8]
    user_payload = {
        "first_name": "Pat",
        "last_name": "Profile",
        "username": f"pat_{suffix}",
        "email": f"pat_{suffix}@example.com",
        "password": password,
        "confirm_password": password,
    }
    reg = client.post("/auth/register", json=user_payload)
    assert reg.status_code == 201, reg.text
    user = reg.json()

    login = client.post(
        "/auth/login",
        json={"username": user_payload["username"], "password": password},
    )
    assert login.status_code == 200, login.text
    return {"user": user, "token": login.json()["access_token"], "password": password}


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------
def test_get_current_user(client: TestClient):
    ctx = _register_and_login(client)
    resp = client.get(
        "/users/me", headers={"Authorization": f"Bearer {ctx['token']}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == ctx["user"]["username"]
    assert body["email"] == ctx["user"]["email"]
    assert body["is_admin"] is False
    # Should NOT leak the password hash.
    assert "password" not in body and "hashed_password" not in body


def test_get_current_user_requires_auth(client: TestClient):
    resp = client.get("/users/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /users/me
# ---------------------------------------------------------------------------
def test_update_current_user_partial(client: TestClient):
    ctx = _register_and_login(client)
    new_first = "Patricia"
    resp = client.put(
        "/users/me",
        headers={"Authorization": f"Bearer {ctx['token']}"},
        json={"first_name": new_first},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["first_name"] == new_first
    # Other fields preserved.
    assert resp.json()["username"] == ctx["user"]["username"]


def test_update_current_user_username_collision(client: TestClient):
    a = _register_and_login(client)
    b = _register_and_login(client)
    # 'b' tries to take 'a's username.
    resp = client.put(
        "/users/me",
        headers={"Authorization": f"Bearer {b['token']}"},
        json={"username": a["user"]["username"]},
    )
    assert resp.status_code == 400
    assert "already in use" in resp.json()["detail"].lower()


def test_update_current_user_empty_body_rejected(client: TestClient):
    ctx = _register_and_login(client)
    resp = client.put(
        "/users/me",
        headers={"Authorization": f"Bearer {ctx['token']}"},
        json={},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /users/me/change-password
# ---------------------------------------------------------------------------
def test_change_password_happy_path(client: TestClient, db_session):
    old = "FirstPass1!"
    new = "BrandNewPass2@"
    ctx = _register_and_login(client, password=old)

    # Wrong current password is rejected.
    bad = client.post(
        "/users/me/change-password",
        headers={"Authorization": f"Bearer {ctx['token']}"},
        json={
            "current_password": "NotMyPass1!",
            "new_password": new,
            "confirm_new_password": new,
        },
    )
    assert bad.status_code == 400
    assert "current password is incorrect" in bad.json()["detail"].lower()

    # Mismatched confirmation is rejected at the schema level (422).
    mismatch = client.post(
        "/users/me/change-password",
        headers={"Authorization": f"Bearer {ctx['token']}"},
        json={
            "current_password": old,
            "new_password": new,
            "confirm_new_password": "Different1!",
        },
    )
    assert mismatch.status_code == 422

    # The successful change.
    ok = client.post(
        "/users/me/change-password",
        headers={"Authorization": f"Bearer {ctx['token']}"},
        json={
            "current_password": old,
            "new_password": new,
            "confirm_new_password": new,
        },
    )
    assert ok.status_code == 200, ok.text
    assert "updated" in ok.json()["detail"].lower()

    # Old password no longer works.
    fail_login = client.post(
        "/auth/login",
        json={"username": ctx["user"]["username"], "password": old},
    )
    assert fail_login.status_code == 401

    # New password works.
    new_login = client.post(
        "/auth/login",
        json={"username": ctx["user"]["username"], "password": new},
    )
    assert new_login.status_code == 200, new_login.text

    # Audit row recorded.
    pc = (
        db_session.query(PasswordChange)
        .filter(PasswordChange.user_id == ctx["user"]["id"])
        .all()
    )
    assert len(pc) == 1
    assert pc[0].user_id == pc[0].changed_by_user_id


def test_change_password_same_as_current_rejected(client: TestClient):
    same = "SamePass11!"
    ctx = _register_and_login(client, password=same)
    resp = client.post(
        "/users/me/change-password",
        headers={"Authorization": f"Bearer {ctx['token']}"},
        json={
            "current_password": same,
            "new_password": same,
            "confirm_new_password": same,
        },
    )
    # PasswordUpdate's validator: "New password must be different..."
    assert resp.status_code == 422


def test_change_password_requires_auth(client: TestClient):
    resp = client.post(
        "/users/me/change-password",
        json={
            "current_password": "Whatever1!",
            "new_password": "Whatever2!",
            "confirm_new_password": "Whatever2!",
        },
    )
    assert resp.status_code == 401
