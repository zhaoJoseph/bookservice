from ..database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from sqlalchemy import ForeignKey
import uuid
from sqlalchemy import Uuid

from ..models import User

class Chat(Base):
    __tablename__ = "chats"

    id : Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    name : Mapped[str] = mapped_column(String(100), nullable=False)
    content : Mapped[str | None] = mapped_column(String(1000000), nullable=True)
    createdAt : Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updatedAt : Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))

    # relationship to ChatMessage; back_populates must match ChatMessage.chat
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id : Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    chat_id : Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("chats.id"))
    user_id : Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    content : Mapped[str] = mapped_column(String(1000000), nullable=False)
    reply : Mapped[str] = mapped_column(String(1000000), nullable=False)
    createdAt : Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updatedAt : Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
    user: Mapped["User"] = relationship("User", back_populates="chat_messages")