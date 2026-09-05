"""
Browser-driven end-to-end test of the registration page.

tests/e2e/test_email_verification_e2e.py drives the app in-process through
FastAPI's TestClient. This instead drives the real templates/register.html
page with Playwright - typing into fields, clicking checkboxes, submitting -
against a real live_server subprocess, and checks the database directly
afterward to confirm what the browser actually sent made it into the
account (not just that the page showed a success message).

This directory is excluded from default pytest collection (see
`norecursedirs` in pytest.ini) even though it lives under tests/e2e/:
pytest-playwright's browser session and pytest-asyncio's "auto" mode (set
project-wide in pytest.ini for the async TestClient tests) don't share a
process well - once Playwright's event-loop bridge has been used, every
async fixture used by *later* tests in the same run starts failing with
"Runner.run() cannot be called from a running event loop", not just
fixtures in this file. Excluding this directory from default recursion
means `pytest`/`pytest tests/` never collects it, so it never shares a
process with the rest of the suite. Run it explicitly with:
`pytest tests/e2e/browser_tests/` (needs `playwright install chromium` once
first).
"""
import sqlite3

import pytest

from tests.e2e.browser_tests.live_server_fixtures import live_server


# tests/conftest.py's `create_tables`/`override_get_db` are async autouse
# fixtures for the in-process TestClient tests, and still apply here as
# ancestor-conftest fixtures even though this directory is excluded from
# default collection (norecursedirs only skips implicit recursion, not
# explicit invocation of this path). This file never touches that in-process
# app/db - it drives a separate live_server subprocess instead - but their
# async event-loop handling clashes with Playwright's own sync/async bridge
# ("Cannot run the event loop while another loop is running"), so they're
# shadowed here with no-op sync versions, scoped to just this file.
@pytest.fixture(scope="session", autouse=True)
def create_tables():
    yield


@pytest.fixture(autouse=True)
def override_get_db():
    yield


@pytest.fixture
def registration_page(live_server, page):
    base_url, db_path = live_server
    page.goto(f"{base_url}/register")
    return page, base_url, db_path


def _fetch_user_row(db_path, email):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT name, email, genres, is_verified FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_registration_form_submits_and_persists_genres(registration_page):
    page, base_url, db_path = registration_page
    email = "browseruser@test.com"

    page.fill("#email", email)
    page.fill("#name", "browseruser")
    page.fill("#password", "Qwertyuiop123@")
    page.fill("#confirm_password", "Qwertyuiop123@")

    chosen_genre_ids = ["1", "2", "3", "4", "5"]
    for genre_id in chosen_genre_ids:
        page.check(f"#g{genre_id}")

    page.click("button[type=submit]")

    # The page's own htmx:beforeSwap handler injects an alert (success or
    # danger) into #login-response once the async htmx request completes -
    # wait for either so a real failure here shows the actual server-side
    # error text instead of a bare Playwright timeout.
    banner = page.locator("#login-response .alert")
    banner.wait_for(timeout=5000)
    assert "alert-success" in (banner.get_attribute("class") or ""), (
        f"registration did not succeed, banner said: {banner.inner_text()!r}"
    )
    assert "Registration successful" in banner.inner_text()

    # The real proof: did the genres the user actually clicked make it to
    # the database? The <input> checkboxes have no `name` attribute unless
    # templates/register.html is fixed, in which case a real browser
    # submission never includes them in the POST body at all - the success
    # banner would still show, silently dropping the user's genre picks.
    row = _fetch_user_row(db_path, email)
    assert row is not None, "no user row was created for the registered email"
    assert row["genres"] == "Action,Adventure,Comedy,Drama,Fantasy"
    assert row["is_verified"] == 0


def test_registration_form_rejects_mismatched_passwords(registration_page):
    page, base_url, db_path = registration_page
    email = "browsermismatch@test.com"

    page.fill("#email", email)
    page.fill("#name", "browsermismatch")
    page.fill("#password", "Qwertyuiop123@")
    page.fill("#confirm_password", "SomethingElse123@")
    for genre_id in ["1", "2", "3", "4", "5"]:
        page.check(f"#g{genre_id}")

    page.click("button[type=submit]")

    # templates/register.html's htmx:confirm handler blocks the request
    # client-side on a password mismatch, so nothing should ever reach the
    # server for this email.
    page.wait_for_timeout(500)
    assert _fetch_user_row(db_path, email) is None


def test_registration_form_rejects_duplicate_email(registration_page):
    page, base_url, db_path = registration_page
    email = "browserduplicate@test.com"

    def _submit(name):
        page.fill("#email", email)
        page.fill("#name", name)
        page.fill("#password", "Qwertyuiop123@")
        page.fill("#confirm_password", "Qwertyuiop123@")
        for genre_id in ["1", "2", "3", "4", "5"]:
            page.check(f"#g{genre_id}")
        page.click("button[type=submit]")

    _submit("browserduplicate")
    banner = page.locator("#login-response .alert")
    banner.wait_for(timeout=5000)
    assert "alert-success" in (banner.get_attribute("class") or ""), (
        f"first registration did not succeed, banner said: {banner.inner_text()!r}"
    )

    # A fresh page load rather than relying on the success handler's
    # form.reset(), so this looks like a genuine second signup attempt.
    page.goto(f"{base_url}/register")
    _submit("browserdupagain")

    banner = page.locator("#login-response .alert")
    banner.wait_for(timeout=5000)
    assert "alert-danger" in (banner.get_attribute("class") or ""), (
        f"duplicate registration should have failed, banner said: {banner.inner_text()!r}"
    )
    assert "Email already exists" in banner.inner_text()

    # The duplicate attempt shouldn't have touched the existing row.
    row = _fetch_user_row(db_path, email)
    assert row is not None
    assert row["name"] == "browserduplicate"

