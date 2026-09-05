from __future__ import annotations
from datetime import datetime
from typing import AsyncGenerator
import uuid

from typing import Optional

from fastapi import Depends, Request
from sqlalchemy import String, DateTime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from fastapi_users.jwt import generate_jwt
from sqlalchemy.orm import relationship

from .schemas import Role, Status
from .database import Base, get_db
from .config import settings

from .aws.client import ses_client
from .auth.utils import fingerprint_verification_token

class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    # --- Custom Fields Only ---
    name: Mapped[str] = mapped_column(String(20), nullable=False)

    # Domain-specific role/status (separate from fastapi-users' is_superuser/is_active)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.user.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=Status.active.value)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    token: Mapped[str] = mapped_column(String(32), nullable=True)
    last_verification_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    createdAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # --- Fastapi-Users Fields ---
    genres: Mapped[list[str]] = mapped_column(String(150), nullable=True)

    # Relationship to chat messages (back_populates in ChatMessage.user)
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")

SECRET = settings.secret_key.get_secret_value()

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def request_verify(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        if not user.is_active:
            raise exceptions.UserInactive()
        if user.is_verified:
            raise exceptions.UserAlreadyVerified()

        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "aud": self.verification_token_audience,
            # Without this, two tokens requested within the same second are
            # byte-for-byte identical (JWTs here otherwise only vary by
            # sub/email/exp, and exp has second resolution), which would
            # break "reject anything but the latest token" in on_after_request_verify.
            "jti": uuid.uuid4().hex,
        }
        token = generate_jwt(
            token_data,
            self.verification_token_secret,
            self.verification_token_lifetime_seconds,
        )
        await self.on_after_request_verify(user, token, request)

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        await self.user_db.update(user, {"token": fingerprint_verification_token(token)})
        ses_client.send_verification_email(
            email=user.email,
            token=token
        )

    async def on_after_verify(
        self, user: User, request: Optional[Request] = None
    ) -> None:
        # Registration leaves status="inactive" (login's actual gate - see
        # src/auth/router.py's /token handler) and is_active=False, but
        # `create(..., safe=True)` silently drops is_active from what's
        # written (it's a privileged field, stripped so registrants can't
        # self-activate), so is_active is already always True regardless.
        # Nothing without this ever flips status back, so a verified user
        # could never actually log in.
        await self.user_db.update(user, {"status": Status.active.value, "is_active": True})


async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)
