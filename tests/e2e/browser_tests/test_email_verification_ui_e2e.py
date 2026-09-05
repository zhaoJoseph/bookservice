"""
Browser-driven end-to-end test of the email verification link.

Registers through the real UI. templates/register.html itself fires the
request-verify-token call right after a successful registration (see its
htmx:beforeSwap handler), so no test here calls that API directly to get the
*first* email - it just waits for the real page to send it, the same as a
real signup. Tests then have the *browser* navigate to the exact link that
was emailed - the same thing a user does by clicking it in their inbox - and
check the result, both the HTTP response and what actually landed in the
database.

AWS can't be faked with the usual in-process `mock_aws()` here: the app runs
in its own subprocess (live_server), and moto's patching only affects the
process that entered it. Instead, live_server_fixtures.py launches the app
via _run_mocked_server.py, which enters mock_aws() for the whole life of
that subprocess and exposes a debug-only /__test__/sent_emails route so this
test (a separate process) can read back what got "sent" over real HTTP.

See test_registration_ui_e2e.py's docstring for why this lives here,
excluded from default pytest collection, and how to run it:
`pytest tests/e2e/browser_tests/`.
"""
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi_users.jwt import generate_jwt
from fastapi_users.manager import VERIFY_USER_TOKEN_AUDIENCE

from tests.e2e.browser_tests.live_server_fixtures import SECRET_KEY, live_server


# See test_registration_ui_e2e.py for why these are shadowed.
@pytest.fixture(scope="session", autouse=True)
def create_tables():
    yield


@pytest.fixture(autouse=True)
def override_get_db():
    yield


def _sent_to(page, base_url, email):
    sent = page.request.get(f"{base_url}/__test__/sent_emails").json()
    return [m for m in sent if m["destinations"]["ToAddresses"] == [email]]


def _wait_for_verification_email(page, base_url, email, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matching = _sent_to(page, base_url, email)
        if matching:
            return matching[-1]
        page.wait_for_timeout(100)
    raise AssertionError(f"no verification email arrived for {email} within {timeout}s")


def _extract_verification_link(message) -> str:
    match = re.search(
        r"https?://[^\s\"'<]+/verify-email\?token=[^\s\"'<]+", message["body"]
    )
    assert match is not None, f"no verification link found in email body: {message['body']!r}"
    return match.group(0)


def _click_verification_link(page, link):
    """Navigates to the real templates/verify.html page and waits for its
    own htmx call to /api/v1/auth/verify to resolve, returning the
    resulting banner locator - the same thing a user sees after clicking
    the link in their inbox."""
    page.goto(link)
    banner = page.locator("#verify-response .alert")
    banner.wait_for(timeout=5000)
    return banner


@pytest.fixture
def registered_user(live_server, page):
    base_url, db_path = live_server
    # live_server is module-scoped (one DB shared by every test in this
    # file), so each test needs its own email to avoid an "already exists"
    # collision.
    email = f"verifyuser-{uuid.uuid4().hex[:8]}@test.com"

    page.goto(f"{base_url}/register")
    page.fill("#email", email)
    page.fill("#name", "verifyuser")
    page.fill("#password", "Qwertyuiop123@")
    page.fill("#confirm_password", "Qwertyuiop123@")
    for genre_id in ["1", "2", "3", "4", "5"]:
        page.check(f"#g{genre_id}")
    page.click("button[type=submit]")

    banner = page.locator("#login-response .alert")
    banner.wait_for(timeout=5000)
    assert "alert-success" in (banner.get_attribute("class") or ""), (
        f"registration did not succeed, banner said: {banner.inner_text()!r}"
    )

    # register.html fires its own request-verify-token call right after
    # this success banner appears; wait for that email to actually show up
    # rather than assuming it's already there.
    _wait_for_verification_email(page, base_url, email)

    return page, base_url, db_path, email


def _is_verified(db_path, email) -> bool:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT is_verified FROM users WHERE email = ?", (email,)
        ).fetchone()
        return bool(row and row[0])
    finally:
        conn.close()


def _user_id(db_path, email) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        assert row is not None, f"no user row found for {email}"
        return row[0]
    finally:
        conn.close()


def _skip_resend_cooldown(db_path, email) -> None:
    # The resend cooldown (VERIFY_RESEND_COOLDOWN_SECONDS, src/auth/router.py)
    # lives in the live_server subprocess, so it can't be monkeypatched from
    # this process the way test_email_verification_e2e.py does in-process.
    # But the cooldown is just "now - last_verification_sent_at", and that
    # timestamp is regular persisted state in the shared SQLite file, so
    # backdating it directly has the same effect as waiting it out for real.
    conn = sqlite3.connect(db_path)
    try:
        backdated = (datetime.now() - timedelta(minutes=5)).isoformat(sep=" ")
        conn.execute(
            "UPDATE users SET last_verification_sent_at = ? WHERE email = ?",
            (backdated, email),
        )
        conn.commit()
    finally:
        conn.close()


def test_clicking_the_emailed_link_verifies_the_account(registered_user):
    page, base_url, db_path, email = registered_user
    assert _is_verified(db_path, email) is False

    verification_link = _extract_verification_link(_sent_to(page, base_url, email)[-1])

    # The actual point of this test: the browser follows the real emailed
    # link (which is only correct at all because SESClient builds it from
    # settings.app_base_url - previously a hardcoded, nonexistent domain) to
    # the real templates/verify.html page, not a URL or API call
    # reconstructed by the test.
    banner = _click_verification_link(page, verification_link)
    assert "alert-success" in (banner.get_attribute("class") or ""), (
        f"verification did not succeed, banner said: {banner.inner_text()!r}"
    )
    assert "verified" in banner.inner_text().lower()

    assert _is_verified(db_path, email) is True


def test_clicking_expired_verification_link_shows_error(registered_user):
    page, base_url, db_path, email = registered_user
    assert _is_verified(db_path, email) is False

    # Building an already-expired token locally rather than waiting out the
    # real one-hour lifetime: UserManager.verification_token_lifetime_seconds
    # lives in the live_server subprocess, so it can't be monkeypatched from
    # this test process the way test_email_verification_e2e.py does
    # in-process. But verification tokens are stateless JWTs signed with
    # SECRET_KEY (shared via live_server_fixtures.py's env), so a token with
    # the same claims and a negative lifetime is indistinguishable to the
    # server from a real one that simply timed out.
    user_id = _user_id(db_path, email)
    expired_token = generate_jwt(
        {"sub": user_id, "email": email, "aud": VERIFY_USER_TOKEN_AUDIENCE, "jti": "expired-test-token"},
        SECRET_KEY,
        -1,
    )

    banner = _click_verification_link(page, f"{base_url}/verify-email?token={expired_token}")
    assert "alert-danger" in (banner.get_attribute("class") or "")
    assert "Invalid token" in banner.inner_text()

    assert _is_verified(db_path, email) is False


def test_clicking_garbage_token_shows_error(registered_user):
    page, base_url, db_path, email = registered_user

    banner = _click_verification_link(page, f"{base_url}/verify-email?token=not-a-real-token")
    assert "alert-danger" in (banner.get_attribute("class") or "")
    assert "Invalid token" in banner.inner_text()


def test_clicking_the_verification_link_twice_fails_the_second_time(registered_user):
    page, base_url, db_path, email = registered_user

    verification_link = _extract_verification_link(_sent_to(page, base_url, email)[-1])

    first_banner = _click_verification_link(page, verification_link)
    assert "alert-success" in (first_banner.get_attribute("class") or "")

    # Same link, second click - as if the user clicked it twice, or opened
    # it from two devices.
    second_banner = _click_verification_link(page, verification_link)
    assert "alert-danger" in (second_banner.get_attribute("class") or "")
    assert "Invalid token" in second_banner.inner_text()


def test_requesting_verification_for_unregistered_email_sends_nothing(live_server, page):
    base_url, _db_path = live_server
    email = f"never-registered-{uuid.uuid4().hex[:8]}@test.com"

    response = page.request.post(
        f"{base_url}/api/v1/auth/request-verify-token",
        form={"email": email},
    )
    # Always 202 regardless of whether the account exists, so this endpoint
    # can't be used to enumerate registered emails.
    assert response.status == 202
    assert _sent_to(page, base_url, email) == []


def test_resend_cooldown_blocks_immediate_retry_and_invalidates_the_old_link(registered_user):
    page, base_url, db_path, email = registered_user
    # registered_user already triggered one send (via register.html's own
    # automatic request-verify-token call) and started the cooldown.
    old_link = _extract_verification_link(_sent_to(page, base_url, email)[-1])

    # Immediately asking again is rejected: the caller has to wait out the
    # resend cooldown before another verification email will be sent.
    retry_resp = page.request.post(
        f"{base_url}/api/v1/auth/request-verify-token",
        form={"email": email},
    )
    assert retry_resp.status == 429

    _skip_resend_cooldown(db_path, email)

    new_resp = page.request.post(
        f"{base_url}/api/v1/auth/request-verify-token",
        form={"email": email},
    )
    assert new_resp.status == 202
    new_link = _extract_verification_link(_sent_to(page, base_url, email)[-1])
    assert new_link != old_link

    # The old link is now stale: only the most recently issued token works.
    stale_banner = _click_verification_link(page, old_link)
    assert "alert-danger" in (stale_banner.get_attribute("class") or "")
    assert "Invalid token" in stale_banner.inner_text()
    assert _is_verified(db_path, email) is False

    # The new one still works.
    fresh_banner = _click_verification_link(page, new_link)
    assert "alert-success" in (fresh_banner.get_attribute("class") or "")
    assert _is_verified(db_path, email) is True


def test_verification_email_fails_when_aws_is_down(registered_user):
    page, base_url, db_path, email = registered_user
    # Skip the cooldown from registered_user's own automatic send, so this
    # attempt is rejected because of the simulated AWS outage below, not
    # because of the resend cooldown.
    _skip_resend_cooldown(db_path, email)

    toggle = page.request.post(f"{base_url}/__test__/simulate_aws_down", params={"down": "true"})
    assert toggle.status == 200
    try:
        response = page.request.post(
            f"{base_url}/api/v1/auth/request-verify-token",
            form={"email": email},
        )
        # Current behavior: nothing between SESClient and the route catches
        # an AWS outage, so it falls through to main.py's catch-all
        # Exception handler as a bare 500 rather than degrading gracefully.
        assert response.status == 500

        # Only the one email from registration - the failed retry sent
        # nothing new.
        assert len(_sent_to(page, base_url, email)) == 1
    finally:
        # This server is shared (module-scoped live_server) - leaving AWS
        # "down" would break every later test in this file.
        reset = page.request.post(f"{base_url}/__test__/simulate_aws_down", params={"down": "false"})
        assert reset.status == 200
