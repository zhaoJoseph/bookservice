from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from .services import LoanService
from ..models import User
from sqlalchemy import select
from .models import Loan

from typing import Annotated, AsyncGenerator

async def get_loan_service(
    db: AsyncSession = Depends(get_db)
) -> AsyncGenerator[LoanService, None]: 
    yield LoanService(db)
