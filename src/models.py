from __future__ import annotations
from datetime import datetime
from typing import AsyncGenerator
import uuid

from typing import Optional

from fastapi import Depends, Request
from sqlalchemy import String, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.orm import relationship

from .schemas import Role, Status
from .database import Base, get_db
from .config import settings

from .aws.client import ses_client

class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    # --- Custom Fields Only ---
    name: Mapped[str] = mapped_column(String(20), nullable=False)

    # Domain-specific role/status (separate from fastapi-users' is_superuser/is_active)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.user.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=Status.active.value)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    token: Mapped[str] = mapped_column(String(32), nullable=True)

    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # --- Fastapi-Users Fields ---
    genres: Mapped[list[str]] = mapped_column(String(50), nullable=True)

    # Relationship to chat messages (back_populates in ChatMessage.user)
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):  
        # Call your AWS client here
        ses_client.send_verification_email(
            email=user.email, 
            token=token
        )

SECRET = settings.secret_key.get_secret_value()

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET


async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)
