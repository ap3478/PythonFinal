"""
Integration tests for the ``/admin/*`` endpoints.

The admin guard requires a real ``users.is_admin = True`` row, so each test
promotes a freshly-registered user via the database session before logging
in. This validates both the positive admin flow and the 403 path for a
non-admin user.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _register(client: TestClient, password: str = "AdminPass1!") -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "first_name": "Adm",
        "last_name": "User",
        "username": f"adm_{suffix}",
        "email": f"adm_{suffix}@example.com",
        "password": password,
        "confirm_password": password,
    }
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return payload


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _promote(db_session, username: str) -> User:
    user = db_session.query(User).filter(User.username == username).first()
    user.is_admin = True
    db_session.commit()
    return user


# ---------------------------------------------------------------------------
# Authorization guard
# ---------------------------------------------------------------------------
def test_admin_endpoints_require_admin(client: TestClient):
    payload = _register(client)
    token = _login(client, payload["username"], payload["password"])
    headers = {"Authorization": f"Bearer {token}"}

    for path in [
        "/admin/users",
        "/admin/calculations",
        "/admin/password-changes",
        "/admin/stats",
    ]:
        r = client.get(path, headers=headers)
        assert r.status_code == 403, f"{path} should be admin-only, got {r.status_code}"


def test_admin_endpoints_require_auth(client: TestClient):
    for path in [
        "/admin/users",
        "/admin/calculations",
        "/admin/password-changes",
        "/admin/stats",
    ]:
        r = client.get(path)
        assert r.status_code == 401, f"{path} should require auth, got {r.status_code}"


# ---------------------------------------------------------------------------
# Happy-path admin views
# ---------------------------------------------------------------------------
def test_admin_lists_users_and_their_calculations(client: TestClient, db_session):
    # Two regular users.
    u_a = _register(client)
    u_b = _register(client)
    tok_a = _login(client, u_a["username"], u_a["password"])
    tok_b = _login(client, u_b["username"], u_b["password"])

    # Each makes a calculation.
    client.post(
        "/calculations",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={"type": "addition", "inputs": [1, 2]},
    )
    client.post(
        "/calculations",
        headers={"Authorization": f"Bearer {tok_b}"},
        json={"type": "power", "inputs": [2, 5]},
    )

    # An admin user.
    admin_payload = _register(client)
    _promote(db_session, admin_payload["username"])
    admin_token = _login(client, admin_payload["username"], admin_payload["password"])
    auth = {"Authorization": f"Bearer {admin_token}"}

    # /admin/users
    r = client.get("/admin/users", headers=auth)
    assert r.status_code == 200
    usernames = {u["username"] for u in r.json()}
    assert {u_a["username"], u_b["username"], admin_payload["username"]} <= usernames
    # Calculation counts surface in this view.
    by_username = {u["username"]: u for u in r.json()}
    assert by_username[u_a["username"]]["calculation_count"] >= 1
    assert by_username[u_b["username"]]["calculation_count"] >= 1

    # /admin/calculations
    r = client.get("/admin/calculations", headers=auth)
    assert r.status_code == 200
    types = {c["type"] for c in r.json()}
    assert {"addition", "power"} <= types

    # Filtered by type.
    r = client.get("/admin/calculations?type=power", headers=auth)
    assert r.status_code == 200
    assert all(c["type"] == "power" for c in r.json())
    assert any(c["username"] == u_b["username"] for c in r.json())

    # /admin/stats
    r = client.get("/admin/stats", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total_users"] >= 3
    assert body["total_calculations"] >= 2
    assert body["calculations_by_type"].get("addition", 0) >= 1


def test_admin_password_change_audit(client: TestClient, db_session):
    # A user changes their password — the admin view should see it.
    user = _register(client, password="OrigA12345!")
    tok = _login(client, user["username"], "OrigA12345!")
    cp = client.post(
        "/users/me/change-password",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "current_password": "OrigA12345!",
            "new_password": "NewA12345!",
            "confirm_new_password": "NewA12345!",
        },
    )
    assert cp.status_code == 200, cp.text

    # Admin promoted and queries the audit endpoint.
    admin = _register(client)
    _promote(db_session, admin["username"])
    admin_tok = _login(client, admin["username"], admin["password"])

    r = client.get(
        "/admin/password-changes",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert any(row["username"] == user["username"] for row in rows)
