from uuid import UUID
import uuid

from sqlalchemy import select
from typing import Sequence

from .exceptions import ChatNotFound
from .models import Chat, ChatMessage


class ChatService:
    def __init__(self, db):
        self.db = db

    async def get_by_id(self, chat_id: UUID) -> Chat | None:
        result = await self.db.execute(select(Chat).where(Chat.id == chat_id))
        return result.scalars().first()

    async def get_id_user(self, chat_id: UUID, user_id: UUID) -> Chat | None:
        result = await self.db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
        return result.scalars().first()

    async def add_chat(self, chat_id: UUID, user_id: UUID, name: str | None = None) -> Chat:
        chat_name = (name or "New Chat").strip() or "New Chat -- " + str(uuid.uuid4().hex[:6])
        chat = Chat(id=chat_id, user_id=user_id, name=chat_name)
        self.db.add(chat)
        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    async def get_chats_for_user(self, user_id: UUID) -> Sequence[Chat]:
        """Return a list of Chat objects belonging to the given user, ordered by updatedAt desc."""
        result = await self.db.execute(select(Chat).where(Chat.user_id == user_id).order_by(Chat.updatedAt.desc()))
        return result.scalars().all()

    async def update_chat(self, chat_id: UUID, content: str | None = None) -> Chat:
        chat = await self.get_by_id(chat_id)
        if not chat:
            raise ChatNotFound()
        if content is not None:
            chat.content = content
            await self.db.commit()
            await self.db.refresh(chat)
        return chat

    async def add_message(self, chat_id: UUID, user_id: UUID, content: str, reply: str = "") -> ChatMessage:
        message = ChatMessage(
            id=uuid.uuid4(),
            chat_id=chat_id,
            user_id=user_id,
            content=content,
            reply=reply,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def update_message_reply(self, message_id: UUID, reply_text: str) -> ChatMessage:
        result = await self.db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
        message = result.scalars().first()
        if not message:
            raise ChatNotFound()
        message.reply = reply_text
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages_for_chat(self, chat_id: UUID, limit: int = 200) -> Sequence[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.createdAt.asc())
            .limit(limit)
        )
        return result.scalars().all()
