import pytest
import requests
from fastapi.testclient import TestClient
from src.main import app
from src.models import User
from src.books.models import Book
from src.chat.models import Chat
from fastapi_users.password import PasswordHelper
from sqlalchemy import insert, select, update
from unittest.mock import Mock

import uuid

password_helper = PasswordHelper()

@pytest.fixture
def mock_rag(monkeypatch):
    """
    Replaces src.chat.router's `requests.post` so tests never hit the real
    external RAG service. `/send/{chat_id}` calls it twice — once against
    `/summarize` (to title a brand-new chat) and once against `/query` (to
    answer the message) — so responses are picked based on the URL.

    Override `calls.summarize_response` / `calls.query_response` (each a
    Mock with `.status_code` and `.json.return_value`) or set
    `calls.raise_on_query = SomeException()` to simulate the external
    service being unreachable.
    """
    class RagCalls:
        def __init__(self):
            self.requests = []  # list[(url, kwargs)] in call order
            self.raise_on_summarize = None
            self.raise_on_query = None

            self.summarize_response = Mock(status_code=200)
            self.summarize_response.json.return_value = {"title": "Mocked Chat Title"}

            self.query_response = Mock(status_code=200)
            self.query_response.json.return_value = {"answer": "Mocked answer"}

    calls = RagCalls()

    def _fake_post(url, **kwargs):
        calls.requests.append((url, kwargs))
        if url.endswith("/summarize"):
            if calls.raise_on_summarize:
                raise calls.raise_on_summarize
            return calls.summarize_response
        if calls.raise_on_query:
            raise calls.raise_on_query
        return calls.query_response

    monkeypatch.setattr("src.chat.router.requests.post", _fake_post)
    return calls

# Base fixture for DB overrides only (no client creation)
@pytest.fixture
def test_db_context(override_get_db, seed_test_data):
    # Just ensures DB is seeded. No client involved.
    yield

@pytest.fixture
def admin_client(test_db_context):
    """
    Creates a FRESH, independent TestClient logged in as ADMIN.
    """
    with TestClient(app) as c:
        # Login
        resp = c.post(
            "/api/v1/auth/token",
            data={"username": "admin@example.com", "password": "password"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Admin login failed: {resp.text}")
        # 'c' now has the admin cookie.
        # Yield it. This 'c' is independent of any other client.
        yield c

@pytest.fixture
def user_client(test_db_context):
    """
    Creates a FRESH, independent TestClient logged in as USER.
    """
    with TestClient(app) as c:
        # Login
        resp = c.post(
            "/api/v1/auth/token",
            data={"username": "user@example.com", "password": "password"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"User login failed: {resp.text}")
        # 'c' now has the user cookie.
        # This 'c' is a DIFFERENT object than the one in admin_client.
        yield c


@pytest.fixture
def client(test_db_context, override_get_db):
    """
    Creates a FRESH, independent TestClient with NO authentication.
    Never logs in, so no auth cookie is ever set — used to test
    endpoints that require a token.
    """
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
async def seed_test_data(db_session, override_get_db):
    hashed = password_helper.hash("password")

    users_data = [
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),  # fixed UUID
            "name": "admin",
            "email": "admin@example.com",
            "hashed_password": hashed,
            "role": "admin",
            "status": "active",
            "is_active": True
        },
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),  # fixed UUID
            "name": "user",
            "email": "user@example.com",
            "hashed_password": hashed,
            "role": "user",
            "status": "active",
            "is_active": True
        },
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
            "name": "suspendeduser",
            "email": "suspended@example.com",
            "hashed_password": hashed,
            "role": "user",
            "status": "suspended",
            "is_active": False
        },
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
            "name": "inactiveuser",
            "email": "inactive@example.com",
            "hashed_password": hashed,
            "role": "user",
            "status": "inactive",
            "is_active": False
        },
    ]

    for user in users_data:
        await db_session.execute(insert(User).values(**user))

    await db_session.execute(insert(Book).values(
        id=1,
        title="Test Book",
        author="Test Author",
        description="A book for testing",
        genre="fiction",
        cover_image_path=None,
        total_copies=10,
        available_copies=10,
        isbn="0000000000001",
    ))

    await db_session.commit()

@pytest.mark.asyncio
async def test_chat_route_get_messages(user_client, make_chat, make_message):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    await make_message(chat_id=chat.id, user_id=user_id, content="Hello there")

    response = user_client.get(
        f"/api/v1/chat/messages/{chat.id}",
    )
    assert response.status_code == 200
    assert response.text.count('class="user-message"') == 1


@pytest.mark.asyncio
async def test_chat_route_get_messages_malformed_chat_id(user_client):
    # not a valid UUID at all, distinct from a well-formed but nonexistent
    # chat_id (see test_chat_route_get_messages_invalid_chat)
    response = user_client.get(
        "/api/v1/chat/messages/not-a-valid-uuid",
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_chat_route_get_messages_invalid_chat(user_client, make_chat, make_message):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # admin@example.com, from seed_test_data
    chat = await make_chat(user_id=user_id, name="test chat")
    await make_message(chat_id=chat.id, user_id=user_id, content="Hello there")

    response = user_client.get(
        f"/api/v1/chat/messages/{uuid.uuid4()}",
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_chat_route_get_messages_wrong_user(user_client, make_chat, make_message):
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000001")  # admin@example.com, from seed_test_data
    chat = await make_chat(user_id=owner_id, name="test chat")
    await make_message(chat_id=chat.id, user_id=owner_id, content="Hello there")

    # user_client is logged in as user@example.com, not the chat's owner
    response = user_client.get(
        f"/api/v1/chat/messages/{chat.id}"
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_chat_route_get_messages_no_token(client, make_chat, make_message):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # admin@example.com, from seed_test_data
    chat = await make_chat(user_id=user_id, name="test chat")
    await make_message(chat_id=chat.id, user_id=user_id, content="Hello there")

    response = client.get(
        f"/api/v1/chat/messages/{chat.id}",
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_chat_route_send_message(user_client, make_chat, make_loan, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "Hello there", "book_id": loan.book_id},
    )
    assert response.status_code == 200
    assert mock_rag.query_response.json.return_value["answer"] in response.text
    assert response.text.count('class="assistant-message"') == 1

@pytest.mark.asyncio
async def test_chat_route_send_message_empty(user_client, make_chat, make_loan, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "", "book_id": loan.book_id},
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_chat_route_send_message_whitespace(user_client, make_chat, make_loan, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "   ", "book_id": loan.book_id},
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_chat_route_send_message_create_chat(user_client, make_loan, mock_rag):
    # /send/{chat_id} returns an HTML fragment, not JSON — there's no
    # "chat_id" field to read back from the response. The server creates the
    # chat under exactly the id we put in the URL, so capture that ourselves.
    chat_id = uuid.uuid4()

    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    response = user_client.post(
        f"/api/v1/chat/send/{chat_id}",
        json={"message": "Hello there", "book_id": loan.book_id},
    )
    assert response.status_code == 200
    assert mock_rag.query_response.json.return_value["answer"] in response.text
    assert response.text.count('class="assistant-message"') == 1

    # both the summarize call (new chat title) and the query call happened
    assert len(mock_rag.requests) == 2
    assert mock_rag.requests[0][0].endswith("/summarize")
    assert mock_rag.requests[1][0].endswith("/query")

    # Ensure the chat was created under the id we requested
    response = user_client.get(
        f"/api/v1/chat/messages/{chat_id}",
    )
    assert response.status_code == 200
    assert response.text.count('class="user-message"') == 1

@pytest.mark.asyncio
async def test_chat_route_send_message_create_chat_no_book_id(user_client, make_loan, make_chat, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    await make_loan(email="user@example.com", status="active", book_id=1)

    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "Hello there ", "book_id": None},
    )
    # no book_id is treated the same as "not one of your active loans" —
    # router.py has no 400 path here, it degrades to a 200 HTML fragment
    assert response.status_code == 200
    assert "You do not have a loan for that book" in response.text

@pytest.mark.asyncio
async def test_chat_route_send_message_create_chat_wrong_loan(user_client, make_loan, make_chat, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "Hello there ", "book_id": loan.book_id + 1},
    )
    assert response.status_code == 200
    assert "You do not have a loan for that book" in response.text

@pytest.mark.asyncio
async def test_chat_route_send_message_wrong_user(user_client, make_loan, make_chat, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")  # admin@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="admin@example.com", status="active", book_id=1)
    await make_loan(email="user@example.com", status="active", book_id=1)

    # user_client (user@example.com) posting to a chat owned by admin — the
    # router treats "chat exists but you're not the owner" as MessageExists
    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "Hello there ", "book_id": loan.book_id},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Message already exists"

@pytest.mark.asyncio
async def test_chat_route_send_message_rag_error(user_client, make_loan, make_chat, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    # a non-200 from the RAG /query call is what the router actually treats
    # as a failure (see src/chat/router.py:299) — the router never returns a
    # 500 itself, it always falls back to a 200 with an apology message
    mock_rag.query_response.status_code = 500

    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "Hello there ", "book_id": loan.book_id},
    )
    assert response.status_code == 200
    assert "I was unable to answer your question" in response.text

@pytest.mark.asyncio
async def test_chat_route_send_message_no_token(client, make_loan, make_chat, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    response = client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "Hello there ", "book_id": loan.book_id},
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_chat_route_send_message_summarize_non_200_fallback_title(user_client, make_loan, mock_rag, db_session):
    # chat_id must NOT already exist — /summarize is only called on chat
    # creation (router.py:363), so this needs a brand-new chat, not make_chat
    chat_id = uuid.uuid4()
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    mock_rag.summarize_response.status_code = 500  # no usable title from RAG

    long_message = "word " * 20  # > 60 chars, exercises the truncation branch
    response = user_client.post(
        f"/api/v1/chat/send/{chat_id}",
        json={"message": long_message.strip(), "book_id": loan.book_id},
    )
    # the rest of the flow (persisting + asking RAG /query) is unaffected —
    # only the chat's title falls back to a truncated snippet of the message
    assert response.status_code == 200
    assert mock_rag.query_response.json.return_value["answer"] in response.text

    result = await db_session.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalars().first()
    assert chat is not None
    assert chat.name.endswith("...")
    assert len(chat.name) <= 63  # 60-char cut + "..."

@pytest.mark.asyncio
async def test_chat_route_send_message_summarize_exception(user_client, make_loan, mock_rag, db_session):
    loan = await make_loan(email="user@example.com", status="active", book_id=1)
    chat_id = uuid.uuid4()

    # /summarize raising should not crash the request — it should fall back
    # to the message-derived title, same as a non-200 response (router.py:184)
    mock_rag.raise_on_summarize = requests.RequestException("boom")

    response = user_client.post(
        f"/api/v1/chat/send/{chat_id}",
        json={"message": "Hello there", "book_id": loan.book_id},
    )
    assert response.status_code == 200
    assert mock_rag.query_response.json.return_value["answer"] in response.text

    result = await db_session.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalars().first()
    assert chat is not None
    assert chat.name == "Hello there"

@pytest.mark.asyncio
async def test_chat_route_send_message_malformed_chat_id(user_client):
    # unlike GET /messages/{chat_id}, the send handler does uuid.UUID(chat_id)
    # with no try/except of its own (router.py:361) — the resulting ValueError
    # is caught by main.py's global @app.exception_handler(ValueError), which
    # maps it to 400, not 404
    response = user_client.post(
        "/api/v1/chat/send/not-a-valid-uuid",
        json={"message": "Hello there", "book_id": 1},
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_chat_route_send_message_list_message(user_client, make_chat, make_loan, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    # router.py unwraps a list "message" to its first element
    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": ["Hello there", "second"], "book_id": loan.book_id},
    )
    assert response.status_code == 200
    assert mock_rag.requests[-1][1]["json"]["question"] == "Hello there"

    response = user_client.get(f"/api/v1/chat/messages/{chat.id}")
    assert "Hello there" in response.text
    assert "second" not in response.text

@pytest.mark.asyncio
async def test_chat_route_send_message_external_id_priority(user_client, make_chat, make_loan, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    # external_id should win over book_id/selected_id — if the priority order
    # were wrong, book_id=9999 (not a loan the user has) would be picked
    # instead and the request would short-circuit to the "no loan" fragment
    # before ever calling RAG at all
    response = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={
            "message": "Hello there",
            "external_id": loan.book_id,
            "book_id": 9999,
            "selected_id": 9999,
        },
    )
    assert response.status_code == 200
    assert mock_rag.query_response.json.return_value["answer"] in response.text
    assert mock_rag.requests[-1][1]["json"]["external_id"] == str(loan.book_id)

@pytest.mark.asyncio
async def test_chat_route_send_message_multiple_messages(user_client, make_chat, make_loan, mock_rag):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data

    chat = await make_chat(user_id=user_id, name="test chat")
    loan = await make_loan(email="user@example.com", status="active", book_id=1)

    mock_rag.query_response.json.return_value = {"answer": "first answer"}
    response1 = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "first message", "book_id": loan.book_id},
    )
    assert response1.status_code == 200

    mock_rag.query_response.json.return_value = {"answer": "second answer"}
    response2 = user_client.post(
        f"/api/v1/chat/send/{chat.id}",
        json={"message": "second message", "book_id": loan.book_id},
    )
    assert response2.status_code == 200

    response = user_client.get(f"/api/v1/chat/messages/{chat.id}")
    assert response.status_code == 200
    assert response.text.count('class="user-message"') == 2
    assert response.text.index("first message") < response.text.index("second message")
    assert "first answer" in response.text
    assert "second answer" in response.text

@pytest.mark.asyncio
async def test_chat_route_get_messages_deactivated_after_login(user_client, make_chat, make_message, db_session):
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")  # user@example.com, from seed_test_data
    chat = await make_chat(user_id=user_id, name="test chat")
    await make_message(chat_id=chat.id, user_id=user_id, content="Hello there")

    # user_client already holds a valid cookie issued while the account was
    # active; fastapi-users' current_active_user re-checks is_active on every
    # request rather than trusting the token at issue time, so deactivating
    # the account afterward should invalidate access immediately
    await db_session.execute(update(User).where(User.id == user_id).values(is_active=False)) # type: ignore[arg-type]
    await db_session.commit()

    response = user_client.get(
        f"/api/v1/chat/messages/{chat.id}",
    )
    assert response.status_code == 401