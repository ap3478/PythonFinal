"""
Integration tests for ``GET /users/me/stats``.

These exercise the report aggregation logic against a real PG database.
We register a fresh user per test (so totals are deterministic), seed
a few calculations of mixed types, then assert the response payload.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _register(client: TestClient) -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "first_name": "Stat",
        "last_name": "User",
        "username": f"stat_{suffix}",
        "email": f"stat_{suffix}@example.com",
        "password": "StrongPass1!",
        "confirm_password": "StrongPass1!",
    }
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201, r.text
    login = client.post(
        "/auth/login",
        json={"username": payload["username"], "password": payload["password"]},
    )
    return {"username": payload["username"], "token": login.json()["access_token"]}


def _create(client: TestClient, token: str, ctype: str, inputs: list) -> dict:
    r = client.post(
        "/calculations",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": ctype, "inputs": inputs},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_stats_empty_for_new_user(client: TestClient):
    ctx = _register(client)
    r = client.get(
        "/users/me/stats", headers={"Authorization": f"Bearer {ctx['token']}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_calculations"] == 0
    assert body["total_operands"] == 0
    assert body["average_operands_per_calculation"] == 0
    assert body["average_result"] is None
    assert body["breakdown"] == []
    assert body["most_used_type"] is None


def test_stats_aggregates_correctly(client: TestClient):
    ctx = _register(client)
    # Three additions and one square_root.
    _create(client, ctx["token"], "addition", [1, 2])           # result 3, 2 inputs
    _create(client, ctx["token"], "addition", [10, 20, 30])     # result 60, 3 inputs
    _create(client, ctx["token"], "addition", [5, 5])           # result 10, 2 inputs
    _create(client, ctx["token"], "square_root", [16])          # result 4, 1 input

    r = client.get(
        "/users/me/stats", headers={"Authorization": f"Bearer {ctx['token']}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_calculations"] == 4
    # 2 + 3 + 2 + 1 = 8 operands total, mean 2.0
    assert body["total_operands"] == 8
    assert body["average_operands_per_calculation"] == 2.0
    # Average of [3, 60, 10, 4] = 19.25
    assert body["average_result"] == pytest.approx(19.25)

    types = {row["type"]: row for row in body["breakdown"]}
    assert types["addition"]["count"] == 3
    assert types["addition"]["average_inputs"] == pytest.approx(2.333, rel=1e-2)
    assert types["square_root"]["count"] == 1
    assert types["square_root"]["average_inputs"] == 1
    assert body["most_used_type"] == "addition"


def test_stats_isolation_between_users(client: TestClient):
    a = _register(client)
    b = _register(client)
    _create(client, a["token"], "addition", [1, 1])
    _create(client, a["token"], "addition", [2, 2])

    r_a = client.get(
        "/users/me/stats", headers={"Authorization": f"Bearer {a['token']}"}
    ).json()
    r_b = client.get(
        "/users/me/stats", headers={"Authorization": f"Bearer {b['token']}"}
    ).json()

    assert r_a["total_calculations"] == 2
    assert r_b["total_calculations"] == 0


def test_stats_requires_auth(client: TestClient):
    r = client.get("/users/me/stats")
    assert r.status_code == 401
