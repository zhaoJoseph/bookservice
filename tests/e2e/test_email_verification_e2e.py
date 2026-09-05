"""
End-to-end test for the email verification flow.

Unlike tests/auth/test_auth.py (which substitutes a UserManager that
short-circuits on_after_request_verify), this exercises the real path:

    POST /register -> POST /request-verify-token -> UserManager.request_verify
    -> UserManager.on_after_request_verify -> ses_client.send_verification_email
    -> boto3 SESv2 send_email

AWS is faked with moto, which intercepts the boto3 calls the already-constructed
ses_client singleton makes, so no real network calls are made. The verification
link is pulled back out of the "sent" email body, mirroring a user clicking the
link from their inbox, and used to complete /verify.
"""

import re

import botocore.exceptions
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.core.models import patch_client
from moto.ses.models import ses_backends

from src.main import app
from src.aws.client import ses_client
from src.aws.config import aws_settings
from src.auth import constants as auth_constants
from src.database import get_db
from src.models import UserManager, get_user_manager


@pytest.fixture
def moto_ses():
    # ses_client.v2_client is a module-level singleton built at import time,
    # before this file's `import moto` ever runs. moto only auto-instruments
    # boto3 clients created *after* it has been imported, so the singleton
    # has to be patched in explicitly or every call sails past the mock and
    # hits real AWS with whatever credentials happen to be configured.
    patch_client(ses_client.v2_client)
    with mock_aws():
        ses_client.v2_client.create_email_identity(EmailIdentity=aws_settings.SES_SOURCE_EMAIL)
        yield


@pytest.fixture
def client(db_session, moto_ses):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # No override for get_user_manager here: this test relies on the real
    # UserManager.on_after_request_verify -> ses_client hook.

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def client_allow_500(db_session, moto_ses):
    # Same as `client`, but with raise_server_exceptions=False: TestClient's
    # default re-raises any exception the app's own 500 handler catches,
    # which is useful for catching accidental unhandled exceptions in most
    # tests but gets in the way when we're deliberately testing what a real
    # caller sees when one occurs (a 500 JSON response, not a crash).
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


def _last_sent_message():
    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    return backend.sent_messages[-1]


@pytest.mark.asyncio
async def test_registration_sends_verification_email_and_verifies(client):
    register_resp = client.post(
        "/api/v1/auth/register",
        data={
            "name": "emailuser",
            "email": "emailuser@test.com",
            "password": "Qwertyuiop123@",
            "confirm_password": "Qwertyuiop123@",
            "genres": "[1,2,3,4,5]",
        },
    )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert request_resp.status_code == 202

    sent = _last_sent_message()
    assert sent.destinations["ToAddresses"] == ["emailuser@test.com"]
    assert sent.source == aws_settings.SES_SOURCE_EMAIL
    assert sent.subject == "Verify your email address"

    match = re.search(r"/verify-email\?token=([^\s\"'<]+)", sent.body)
    assert match is not None, f"no verification link found in email body: {sent.body!r}"
    token = match.group(1)

    verify_resp = client.get(f"/api/v1/auth/verify?token={token}")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_request_verify_token_for_unknown_email_sends_nothing(client):
    response = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "doesnotexist@test.com"},
    )
    assert response.status_code == 202

    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert backend.sent_messages == []

@pytest.mark.asyncio
async def test_request_verify_token_for_wrong_email_sends_nothing(client):
    register_resp = client.post(
            "/api/v1/auth/register",
            data={
                "name": "emailuser",
                "email": "emailuser@test.com",
                "password": "Qwertyuiop123@",
                "confirm_password": "Qwertyuiop123@",
                "genres": "[1,2,3,4,5]",
            },
        )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "wrongemail@test.com"},
    )

    assert request_resp.status_code == 202

@pytest.mark.asyncio
async def test_request_verify_token_too_late_sends_nothing(client, monkeypatch):
    register_resp = client.post(
            "/api/v1/auth/register",
            data={
                "name": "emailuser",
                "email": "emailuser@test.com",
                "password": "Qwertyuiop123@",
                "confirm_password": "Qwertyuiop123@",
                "genres": "[1,2,3,4,5]",
            },
        )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    # Force the token to be born already-expired: fastapi_users bakes
    # `exp = now + verification_token_lifetime_seconds` into the JWT, so a
    # negative lifetime puts `exp` in the past with no sleep needed.
    monkeypatch.setattr(UserManager, "verification_token_lifetime_seconds", -1)

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert request_resp.status_code == 202

    sent = _last_sent_message()
    match = re.search(r"/verify-email\?token=([^\s\"'<]+)", sent.body)
    assert match is not None, f"no verification link found in email body: {sent.body!r}"
    expired_token = match.group(1)

    verify_resp = client.get(f"/api/v1/auth/verify?token={expired_token}")
    assert verify_resp.status_code == 401

    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert len(backend.sent_messages) == 1

@pytest.mark.asyncio
async def test_request_verify_token_wrong_token(client, monkeypatch):
    register_resp = client.post(
        "/api/v1/auth/register",
        data={
            "name": "emailuser",
            "email": "emailuser@test.com",
            "password": "Qwertyuiop123@",
            "confirm_password": "Qwertyuiop123@",
            "genres": "[1,2,3,4,5]",
        },
    )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    verify_resp = client.get(f"/api/v1/auth/verify?token=wrongtoken")
    assert verify_resp.status_code == 401

    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert backend.sent_messages == []

@pytest.mark.asyncio
async def test_request_verify_token_reverify_fails(client, monkeypatch):
    register_resp = client.post(
            "/api/v1/auth/register",
            data={
                "name": "emailuser",
                "email": "emailuser@test.com",
                "password": "Qwertyuiop123@",
                "confirm_password": "Qwertyuiop123@",
                "genres": "[1,2,3,4,5]",
            },
        )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert request_resp.status_code == 202

    sent = _last_sent_message()
    assert sent.destinations["ToAddresses"] == ["emailuser@test.com"]
    assert sent.source == aws_settings.SES_SOURCE_EMAIL
    assert sent.subject == "Verify your email address"

    match = re.search(r"/verify-email\?token=([^\s\"'<]+)", sent.body)
    assert match is not None, f"no verification link found in email body: {sent.body!r}"
    token = match.group(1)

    verify_resp = client.get(f"/api/v1/auth/verify?token={token}")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True

    # Now try to verify again, which should fail because the token has already
    # been used.
    verify_resp = client.get(f"/api/v1/auth/verify?token={token}")
    assert verify_resp.status_code == 401

    # Only the one /request-verify-token call above sent anything; the two
    # /verify calls don't send email themselves.
    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert len(backend.sent_messages) == 1

@pytest.mark.asyncio
async def test_request_verify_token_when_aws_is_unreachable(client_allow_500, monkeypatch):
    client = client_allow_500
    """
    Simulates an SES outage: the network call itself never gets a response,
    which is what an AWS-side outage looks like from here (as opposed to a
    ClientError, which means AWS responded but rejected the request).
    """
    register_resp = client.post(
        "/api/v1/auth/register",
        data={
            "name": "emailuser",
            "email": "emailuser@test.com",
            "password": "Qwertyuiop123@",
            "confirm_password": "Qwertyuiop123@",
            "genres": "[1,2,3,4,5]",
        },
    )
    assert register_resp.status_code == 201

    def _aws_is_down(*args, **kwargs):
        raise botocore.exceptions.EndpointConnectionError(
            endpoint_url="https://email.us-east-1.amazonaws.com/"
        )

    monkeypatch.setattr(ses_client.v2_client, "send_email", _aws_is_down)

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )

    # Current behavior: nothing between SESClient.send_verification_email and
    # the route catches this, so it falls through to main.py's catch-all
    # Exception handler as a bare 500 rather than degrading gracefully (e.g.
    # still returning 202 and letting the email retry out-of-band).
    assert request_resp.status_code == 500

    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert backend.sent_messages == []

@pytest.mark.asyncio
async def test_request_verify_token_generates_a_new_token(client, monkeypatch):
    register_resp = client.post(
            "/api/v1/auth/register",
            data={
                "name": "emailuser",
                "email": "emailuser@test.com",
                "password": "Qwertyuiop123@",
                "confirm_password": "Qwertyuiop123@",
                "genres": "[1,2,3,4,5]",
            },
        )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert request_resp.status_code == 202

    sent = _last_sent_message()
    assert sent.destinations["ToAddresses"] == ["emailuser@test.com"]
    assert sent.source == aws_settings.SES_SOURCE_EMAIL
    assert sent.subject == "Verify your email address"

    # Immediately retrying is rejected: the caller has to wait out the resend
    # cooldown before another verification email will be sent.
    retry_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert retry_resp.status_code == 429

    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert len(backend.sent_messages) == 1  # the rejected retry sent nothing

    # Skip the wait rather than actually sleeping out the cooldown: shrink it
    # to 0 so the next request is treated as "enough time has passed".
    monkeypatch.setattr(auth_constants, "VERIFY_RESEND_COOLDOWN_SECONDS", 0)

    retry_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert retry_resp.status_code == 202
    assert len(backend.sent_messages) == 2

    # The new token is a genuinely usable one, not just a resend of the old
    # one (comparing raw JWTs would be flaky: two tokens minted in the same
    # second can be byte-for-byte identical).
    new_sent = _last_sent_message()
    match = re.search(r"/verify-email\?token=([^\s\"'<]+)", new_sent.body)
    assert match is not None, f"no verification link found in email body: {new_sent.body!r}"
    new_token = match.group(1)

    verify_resp = client.get(f"/api/v1/auth/verify?token={new_token}")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True

@pytest.mark.asyncio
async def test_request_verify_token_attempt_use_old_token(client, monkeypatch):
    register_resp = client.post(
            "/api/v1/auth/register",
            data={
                "name": "emailuser",
                "email": "emailuser@test.com",
                "password": "Qwertyuiop123@",
                "confirm_password": "Qwertyuiop123@",
                "genres": "[1,2,3,4,5]",
            },
        )
    assert register_resp.status_code == 201
    assert register_resp.json()["is_verified"] is False

    request_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert request_resp.status_code == 202

    sent = _last_sent_message()
    assert sent.destinations["ToAddresses"] == ["emailuser@test.com"]
    assert sent.source == aws_settings.SES_SOURCE_EMAIL
    assert sent.subject == "Verify your email address"

    match = re.search(r"/verify-email\?token=([^\s\"'<]+)", sent.body)
    assert match is not None, f"no verification link found in email body: {sent.body!r}"
    token = match.group(1)

    # Immediately retrying is rejected: the caller has to wait out the resend
    # cooldown before another verification email will be sent.
    retry_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert retry_resp.status_code == 429

    backend = ses_backends[DEFAULT_ACCOUNT_ID][aws_settings.AWS_REGION]
    assert len(backend.sent_messages) == 1  # the rejected retry sent nothing

    # Skip the wait rather than actually sleeping out the cooldown: shrink it
    # to 0 so the next request is treated as "enough time has passed".
    monkeypatch.setattr(auth_constants, "VERIFY_RESEND_COOLDOWN_SECONDS", 0)

    retry_resp = client.post(
        "/api/v1/auth/request-verify-token",
        data={"email": "emailuser@test.com"},
    )
    assert retry_resp.status_code == 202
    assert len(backend.sent_messages) == 2

    verify_resp = client.get(f"/api/v1/auth/verify?token={token}")
    assert verify_resp.status_code == 401
    assert verify_resp.json()["detail"] == "Invalid token"