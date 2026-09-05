"""
Browser-driven end-to-end test of the login page (templates/login.html).

Registration and email verification are already covered by
test_registration_ui_e2e.py and test_email_verification_ui_e2e.py, so the
setup here (register + verify) goes through the API directly via
page.request rather than the UI again - this file's focus is what happens
when a real user submits the login form: does the browser end up logged in
(cookie set, redirected to /catalog) or shown the right error.

See test_registration_ui_e2e.py's docstring for why this lives here,
excluded from default pytest collection, and how to run it:
`pytest tests/e2e/browser_tests/`.
"""
import re

import pytest

from tests.e2e.browser_tests.live_server_fixtures import live_server


# See test_registration_ui_e2e.py for why these are shadowed.
@pytest.fixture(scope="session", autouse=True)
def create_tables():
    yield


@pytest.fixture(autouse=True)
def override_get_db():
    yield


def _register(page, base_url, email, password, name):
    resp = page.request.post(
        f"{base_url}/api/v1/auth/register",
        form={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
            "genres": "[1,2,3,4,5]",
        },
    )
    assert resp.status == 201, resp.text()


def _verify(page, base_url, email):
    resp = page.request.post(
        f"{base_url}/api/v1/auth/request-verify-token",
        form={"email": email},
    )
    assert resp.status == 202, resp.text()

    sent = page.request.get(f"{base_url}/__test__/sent_emails").json()
    matching = [m for m in sent if m["destinations"]["ToAddresses"] == [email]]
    assert matching, f"no verification email sent to {email}; sent: {sent!r}"

    # The emailed link points at templates/verify.html (see
    # test_email_verification_ui_e2e.py for that page's own coverage); this
    # file's focus is login, so it just extracts the token and hits the
    # underlying API directly rather than going through that page too.
    match = re.search(
        r"/verify-email\?token=([^\s\"'<]+)",
        matching[-1]["body"],
    )
    assert match is not None, f"no verification link in email body: {matching[-1]['body']!r}"

    verify_resp = page.request.get(f"{base_url}/api/v1/auth/verify?token={match.group(1)}")
    assert verify_resp.status == 200, verify_resp.text()


def _login_error_banner(page):
    banner = page.locator("#login-response .alert")
    banner.wait_for(timeout=5000)
    return banner


def test_login_success_redirects_to_catalog(live_server, page):
    base_url, _db_path = live_server
    email = "loginsuccess@test.com"
    password = "Qwertyuiop123@"
    _register(page, base_url, email, password, name="loginsuccess")
    _verify(page, base_url, email)

    page.goto(f"{base_url}/login")
    page.fill("#username", email)
    page.fill("#password", password)
    page.click("button[type=submit]")

    # A successful /api/v1/auth/token response sets an HX-Redirect header,
    # which htmx follows as a full browser navigation - the real proof
    # login worked, not just that the request returned 200.
    page.wait_for_url(f"{base_url}/catalog", timeout=5000)

    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    assert "access_token" in cookies, f"no access_token cookie after login; got: {cookies!r}"


def test_login_failure_wrong_password(live_server, page):
    base_url, _db_path = live_server
    email = "loginwrongpw@test.com"
    password = "Qwertyuiop123@"
    _register(page, base_url, email, password, name="loginwrongpw")

    page.goto(f"{base_url}/login")
    page.fill("#username", email)
    page.fill("#password", "TotallyWrongPassword123@")
    page.click("button[type=submit]")

    banner = _login_error_banner(page)
    assert "alert-danger" in (banner.get_attribute("class") or "")
    assert "Incorrect email or password" in banner.inner_text()
    assert page.url == f"{base_url}/login"


def test_login_failure_before_email_verification(live_server, page):
    base_url, _db_path = live_server
    email = "loginunverified@test.com"
    password = "Qwertyuiop123@"
    _register(page, base_url, email, password, name="loginunverified")
    # Deliberately not verifying - registration alone shouldn't be enough
    # to log in.

    page.goto(f"{base_url}/login")
    page.fill("#username", email)
    page.fill("#password", password)
    page.click("button[type=submit]")

    banner = _login_error_banner(page)
    assert "alert-danger" in (banner.get_attribute("class") or "")
    assert "suspended" in banner.inner_text().lower()
    assert page.url == f"{base_url}/login"
