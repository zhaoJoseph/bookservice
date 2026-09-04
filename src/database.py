import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import pool
import uuid

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bookservice.db")
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

engine_kwargs = {
    "poolclass": pool.NullPool,
    "future": True,
}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # sqlite (aiosqlite) uses the stdlib sqlite3 module which doesn't accept
    # asyncpg-specific connection kwargs such as prepared_statement_name_func.
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # For asyncpg / other drivers, pass tuning options (e.g., for PostgreSQL).
    engine_kwargs["connect_args"] = {
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    **engine_kwargs,
)


async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

async def get_db():
    async with SessionLocal() as db:
        yield db