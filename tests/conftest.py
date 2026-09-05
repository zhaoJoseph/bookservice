import os

# Tests must never touch real AWS. These have to be set before src.main (and
# therefore src.aws.config.aws_settings) is imported anywhere in the suite,
# since that singleton reads them once at import time. Mirrors the dummy
# values CI sets via job env in .github/workflows/ci.yml.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("SES_SOURCE_EMAIL", "test@example.com")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("TESTING", "true")

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import delete, select

from src.main import app
import src.database as db_module
from src.models import Base, User

from src.models import Base, User

from datetime import datetime, timedelta

import uuid

try:
    from src.books.models import Book
except ImportError:
    Book = None

try:
    from src.loans.models import Loan
except ImportError:
    Loan = None

try:
    from src.chat.models import Chat, ChatMessage
except ImportError:
    Chat = None
    ChatMessage = None

# 1. Create a test engine with async
SQLALCHEMY_TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Create tables once per session
@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

# 2. The per-test session fixture
@pytest.fixture
async def db_session():
    # Create a session for this test
    async_session = async_sessionmaker(
        bind=engine, 
        class_=AsyncSession, 
        autocommit=False, 
        autoflush=False,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        try:
            await session.rollback()
        except Exception:
            pass

        # Now clean up all tables in FK-safe order
        for table in [ChatMessage, Chat, Loan, Book, User]:
            try:
                await session.execute(delete(table))
                await session.commit()
            except Exception:
                try:
                    await session.rollback()
                except Exception:
                    pass

@pytest.fixture(autouse=True)
async def override_get_db(db_session):
    # Patch the module-level SessionLocal to use test engine
    original_session_local = db_module.SessionLocal
    
    test_session_local = async_sessionmaker(
        bind=engine,  # test engine
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    SessionLocal = test_session_local

    # Also override get_db for routes that use Depends(get_db)
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[db_module.get_db] = _override_get_db
    
    yield
    
    db_module.SessionLocal = original_session_local
    app.dependency_overrides.clear()

@pytest.fixture
async def make_loan(db_session, seed_test_data):
    """Factory fixture — call it in your test with whatever params you need."""
    created_loans = []

    async def _make_loan(email="user@example.com", status="active", book_id=1):

        if Loan is None:
            raise Exception("Loan model not found")

        result = await db_session.execute(
            select(User).where(User.email == email)  # type: ignore[arg-type]
        )
        user = result.scalars().first()

        if Book is None:
            raise Exception("Book model not found")

        book_result = await db_session.execute(
            select(Book).where(Book.id == book_id)
        )
        book = book_result.scalars().first()
        if not book:
            raise Exception(f"Book {book_id} not found in test DB")

        loan_data = {
            "borrower_id": user.id,
            "book_id": book_id,
            "status": status,
            "requested_at": datetime.now() - timedelta(days=5),
        }

        if status == "active":
            loan_data["approved_at"] = datetime.now() - timedelta(days=3)
            loan_data["due_date"] = datetime.now() + timedelta(days=14)
            book.available_copies -= 1
        elif status == "returned":
            loan_data["approved_at"] = datetime.now() - timedelta(days=3)
            loan_data["due_date"] = datetime.now() + timedelta(days=14)
            loan_data["returned_at"] = datetime.now() - timedelta(days=1)

        loan = Loan(**loan_data)
        db_session.add(loan)
        await db_session.commit()
        await db_session.refresh(loan)
        created_loans.append(loan)
        return loan

    yield _make_loan

    for loan in created_loans:
        try:
            await db_session.delete(loan)
        except Exception:
            pass
    await db_session.commit()

@pytest.fixture
async def make_chat(db_session, seed_test_data):
    """Factory fixture — call it in your test with whatever params you need."""
    created_chats = []

    async def _make_chat(user_id: uuid.UUID, name: str | None = None):
        if Chat is None:
            raise Exception("Chat model not found")
        
        chat_data = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "name": name or "test chat",
            "content": None,
        }
        chat = Chat(**chat_data)
        db_session.add(chat)
        await db_session.commit()
        await db_session.refresh(chat)
        created_chats.append(chat)
        return chat

    yield _make_chat

    for chat in created_chats:
        try:
            await db_session.delete(chat)
        except Exception:
            pass
    await db_session.commit()

@pytest.fixture
async def make_message(db_session, seed_test_data):
    """Factory fixture — call it in your test with whatever params you need."""
    created_messages = []

    async def _make_message(chat_id: uuid.UUID, user_id: uuid.UUID, content: str = "test message", reply: str = ""):
        if ChatMessage is None:
            raise Exception("ChatMessage model not found")

        message = ChatMessage(
            id=uuid.uuid4(),
            chat_id=chat_id,
            user_id=user_id,
            content=content,
            reply=reply,
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)
        created_messages.append(message)
        return message

    yield _make_message

    for message in created_messages:
        try:
            await db_session.delete(message)
        except Exception:
            pass
    await db_session.commit()

# Clean up test DB after test
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    yield
    import os
    if os.path.exists("./test.db"):
        os.remove("./test.db")

