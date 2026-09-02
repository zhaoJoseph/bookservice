from fastapi import Depends, HTTPException, status
from typing import Annotated, AsyncGenerator
from ..models import User, Role
from ..auth.dependencies import current_active_user
from .services import BookService
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db

async def get_book_service(
    db: AsyncSession = Depends(get_db)
) -> AsyncGenerator[BookService, None]: 
    yield BookService(db)

def is_admin(user: User):
    return user.role == Role.admin

async def require_admin(
    user: Annotated[User, Depends(current_active_user)],
) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not admin")
    return user