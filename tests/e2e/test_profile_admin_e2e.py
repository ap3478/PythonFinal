"""
End-to-end browser tests for the new feature set.

These exercise the real UI through Playwright: register → login → use the
new operation types → view stats → update profile → change password →
re-login. A separate test promotes a user to admin and confirms the
admin dashboard renders the rows.
"""

from uuid import uuid4
from typing import Optional
import pytest
import requests
from playwright.sync_api import expect

from app.database import SessionLocal
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_user(suffix: Optional[str] = None, password: str = "OrigPass1!") -> dict:
    suffix = suffix or uuid4().hex[:8]
    return {
        "first_name": "E2E",
        "last_name": "Tester",
        "username": f"e2e_{suffix}",
        "email": f"e2e_{suffix}@example.com",
        "password": password,
        "confirm_password": password,
    }


def _register_via_api(base_url: str, payload: dict) -> None:
    resp = requests.post(f"{base_url.rstrip('/')}/auth/register", json=payload)
    assert resp.status_code == 201, resp.text


def _login_in_browser(page, base_url: str, username: str, password: str) -> None:
    page.goto(f"{base_url.rstrip('/')}/login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard", timeout=10_000)


# ---------------------------------------------------------------------------
# New operation type via the dashboard UI
# ---------------------------------------------------------------------------
def test_new_calc_type_square_root_in_ui(page, fastapi_server):
    payload = _make_user()
    _register_via_api(fastapi_server, payload)
    _login_in_browser(page, fastapi_server, payload["username"], payload["password"])

    # Pick square_root and submit a single input.
    page.select_option("#calcType", "square_root")
    expect(page.locator("#calcInputsHint")).to_have_text(
        "Exactly one non-negative number."
    )
    page.fill("#calcInputs", "144")
    page.click('#calculationForm button[type="submit"]')

    # The new row must appear in the calculations table.
    table = page.locator("#calculationsTable")
    expect(table).to_contain_text("square_root", timeout=10_000)
    expect(table).to_contain_text("12")  # sqrt(144)


def test_new_calc_type_power_in_ui(page, fastapi_server):
    payload = _make_user()
    _register_via_api(fastapi_server, payload)
    _login_in_browser(page, fastapi_server, payload["username"], payload["password"])

    page.select_option("#calcType", "power")
    page.fill("#calcInputs", "2, 10")
    page.click('#calculationForm button[type="submit"]')

    table = page.locator("#calculationsTable")
    expect(table).to_contain_text("power", timeout=10_000)
    expect(table).to_contain_text("1024")  # 2 ** 10


# ---------------------------------------------------------------------------
# Profile + change password flow
# ---------------------------------------------------------------------------
def test_profile_update_flow(page, fastapi_server):
    payload = _make_user()
    _register_via_api(fastapi_server, payload)
    _login_in_browser(page, fastapi_server, payload["username"], payload["password"])

    page.goto(f"{fastapi_server.rstrip('/')}/profile")
    expect(page.locator("#profileFirstName")).to_have_value("E2E")

    page.fill("#profileFirstName", "Updated")
    page.click("#profileSaveBtn")
    expect(page.locator("#profileAlerts")).to_contain_text("Profile updated.")

    # Reload and confirm persistence.
    page.reload()
    expect(page.locator("#profileFirstName")).to_have_value("Updated")


def test_password_change_then_relogin(page, fastapi_server):
    old = "FirstE2E1!"
    new = "SecondE2E2@"
    payload = _make_user(password=old)
    _register_via_api(fastapi_server, payload)
    _login_in_browser(page, fastapi_server, payload["username"], old)

    # Negative path — wrong current password
    page.goto(f"{fastapi_server.rstrip('/')}/profile")
    page.fill("#currentPassword", "WrongPass1!")
    page.fill("#newPassword", new)
    page.fill("#confirmNewPassword", new)
    page.click("#passwordSaveBtn")
    expect(page.locator("#profileAlerts")).to_contain_text(
        "Current password is incorrect"
    )

    # Happy path
    page.fill("#currentPassword", old)
    page.fill("#newPassword", new)
    page.fill("#confirmNewPassword", new)
    page.click("#passwordSaveBtn")
    expect(page.locator("#profileAlerts")).to_contain_text("Password updated")

    # The page kicks the user to /login after a beat.
    page.wait_for_url("**/login", timeout=10_000)

    # Old password no longer works.
    page.fill("#username", payload["username"])
    page.fill("#password", old)
    page.click('button[type="submit"]')
    assert "/login" in page.url # still on /login

    # New password does.
    page.fill("#username", payload["username"])
    page.fill("#password", new)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard", timeout=10_000)


# ---------------------------------------------------------------------------
# Stats page
# ---------------------------------------------------------------------------
def test_stats_page_shows_counts(page, fastapi_server):
    payload = _make_user()
    _register_via_api(fastapi_server, payload)
    _login_in_browser(page, fastapi_server, payload["username"], payload["password"])

    # Make two calculations of different types.
    for ctype, inputs in [("addition", "1, 2"), ("modulus", "10, 3")]:
        page.select_option("#calcType", ctype)
        page.fill("#calcInputs", inputs)
        page.click('#calculationForm button[type="submit"]')
        page.wait_for_timeout(300)

    page.goto(f"{fastapi_server.rstrip('/')}/stats")
    expect(page.locator("#statTotal")).to_have_text("2", timeout=10_000)
    breakdown = page.locator("#statsBreakdown")
    expect(breakdown).to_contain_text("addition")
    expect(breakdown).to_contain_text("modulus")


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------
def test_admin_view_for_promoted_user(page, fastapi_server, db_session):
    # Make a couple of regular users with calculations.
    other = _make_user()
    _register_via_api(fastapi_server, other)
    other_login = requests.post(
        f"{fastapi_server.rstrip('/')}/auth/login",
        json={"username": other["username"], "password": other["password"]},
    ).json()
    requests.post(
        f"{fastapi_server.rstrip('/')}/calculations",
        headers={"Authorization": f"Bearer {other_login['access_token']}"},
        json={"type": "addition", "inputs": [1, 2]},
    )

    admin = _make_user()
    _register_via_api(fastapi_server, admin)

    # Promote in the database.
    user = (
        db_session.query(User).filter(User.username == admin["username"]).first()
    )
    user.is_admin = True
    db_session.commit()

    _login_in_browser(page, fastapi_server, admin["username"], admin["password"])
    page.goto(f"{fastapi_server.rstrip('/')}/admin")

    # The admin nav link should be visible too.
    expect(page.locator("#navAdmin")).to_be_visible()
    # The users tab is loaded by default.
    body = page.locator("#adminUsersBody")
    expect(body).to_contain_text(other["username"], timeout=10_000)
    expect(body).to_contain_text(admin["username"])

    # Switch to the calculations tab.
    page.click('button[data-tab="calcs"]')
    expect(page.locator("#adminCalcsBody")).to_contain_text("addition")


def test_admin_view_forbidden_for_regular_user(page, fastapi_server):
    payload = _make_user()
    _register_via_api(fastapi_server, payload)
    _login_in_browser(page, fastapi_server, payload["username"], payload["password"])

    page.goto(f"{fastapi_server.rstrip('/')}/admin")
    expect(page.locator("#adminGate")).to_be_visible(timeout=10_000)
    expect(page.locator("#adminContent")).to_be_hidden()
