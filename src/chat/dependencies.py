from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from .services import ChatService

from typing import Annotated, AsyncGenerator

async def get_chat_service(
    db : AsyncSession = Depends(get_db)
) -> AsyncGenerator[ChatService, None]: 
    yield ChatService(db)