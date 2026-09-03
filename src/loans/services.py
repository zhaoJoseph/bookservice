from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_, and_
from sqlalchemy.orm import selectinload
from .models import Loan
from ..books.models import Book
from ..models import User

from .schemas import LoanListQuery, LoanListQueryAdmin, LoanUpdate, LoanPublic

from datetime import datetime

from .exceptions import LoanNotFound, ValidationError, LoanAlreadyExists, WrongUser, LoanNotActive
from ..books.exceptions import BookNotFound

from typing import Sequence, Tuple

from ..utils import parse_csv_param

from ..models import User, Role

import uuid

class LoanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, loan_id: int, user: User) -> Loan:
        stmt = (
            select(Loan)
            .where(Loan.id == loan_id)
            .options(selectinload(Loan.book), selectinload(Loan.borrower))
        )
        result = await self.db.execute(stmt)
        loan = result.scalars().first()
        if not loan:
            raise LoanNotFound()

        if user.role == Role.admin:
            return loan

        if loan.borrower_id != user.id:
            raise WrongUser()

        return loan

    async def list_loans(self, query: LoanListQuery, borrower_id:  uuid.UUID | None = None) -> Tuple[Sequence[Loan], int]:
        stmt = select(Loan).join(Book, Loan.book_id == Book.id)

        if borrower_id is not None:
            # borrower_id is UUID — compare directly
            if isinstance(borrower_id, str):
                try:
                    borrower_id = uuid.UUID(borrower_id)
                except ValueError:
                    # invalid id, return empty
                    return [], 0
            stmt = stmt.where(Loan.borrower_id == borrower_id)
        if query.status:
            stmt = stmt.where(Loan.status == query.status)
        if query.title:
            stmt = stmt.where(Book.title.ilike(f"%{query.title}%"))
        if query.author:
            stmt = stmt.where(Book.author.ilike(f"%{query.author}%"))
        if query.isbn:
            stmt = stmt.where(Book.isbn.ilike(f"%{query.isbn}%"))
        if query.genre:
            stmt = stmt.where(Book.genre == query.genre)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt) or 0

        limit = query.limit or 20
        offset = ((query.page or 1) - 1) * limit

        stmt = (
            stmt.options(selectinload(Loan.book), selectinload(Loan.borrower))
            .offset(offset)
            .limit(limit)
            .order_by(Loan.requested_at.desc())
        )

        result = await self.db.execute(stmt)
        loans = result.scalars().all()

        return loans, total


    async def list_loans_admin(self, query: LoanListQueryAdmin) -> Tuple[Sequence[Loan], int]:
        stmt = select(Loan).join(Book, Loan.book_id == Book.id)

        if query.email:
            stmt = stmt.join(User, Loan.borrower_id == User.id)
            emails = parse_csv_param(query.email)
            if emails:
                stmt = stmt.where(or_(*[User.email.ilike(f"%{e}%") for e in emails])) # type: ignore[attr-defined]

        raw_ids = parse_csv_param(query.id)
        if raw_ids:
            parsed_ids = []
            for id in raw_ids:
                try:
                    parsed_ids.append(int(id))
                except ValueError:
                    pass
            stmt = stmt.where(Loan.id.in_(parsed_ids))

        statuses = parse_csv_param(query.status)
        if statuses:
            stmt = stmt.where(Loan.status.in_(statuses))

        titles = parse_csv_param(query.title)
        if titles:
            stmt = stmt.where(or_(*[Book.title.ilike(f"%{t}%") for t in titles]))

        authors = parse_csv_param(query.author)
        if authors:
            stmt = stmt.where(or_(*[Book.author.ilike(f"%{a}%") for a in authors]))

        isbns = parse_csv_param(query.isbn)
        if isbns:
            stmt = stmt.where(or_(*[Book.isbn.ilike(f"%{i}%") for i in isbns]))

        genres = parse_csv_param(query.genre)
        if genres:
            stmt = stmt.where(Book.genre.in_(genres))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt) or 0

        limit = query.limit or 20
        offset = ((query.page or 1) - 1) * limit

        stmt = (
            stmt.options(selectinload(Loan.book), selectinload(Loan.borrower))
            .offset(offset)
            .limit(limit)
            .order_by(Loan.requested_at.desc())
        )
        result = await self.db.execute(stmt)
        loans = result.scalars().all()
        return loans, total

    async def update_loan(self, loan_id: int, loan_in: LoanUpdate, user: User) -> Loan:
        loan = await self.get_by_id(loan_id, user)

        if loan.status == "rejected" or loan.status == "returned":
            raise ValidationError(detail="Loan cannot be updated")
        
        if loan_in.due_date:
                parsed_due_date = datetime.fromisoformat(loan_in.due_date)
                if parsed_due_date < loan.requested_at:
                    raise ValidationError(detail="Due date cannot be before requested at")
                loan.due_date = parsed_due_date

        if loan_in.approved_at:
            parsed_approved_at = datetime.fromisoformat(loan_in.approved_at)
            if parsed_approved_at < loan.requested_at:
                raise ValidationError(detail="Approved at cannot be before requested at")
            loan.approved_at = parsed_approved_at

        if loan_in.returned_at:
            parsed_returned_at = datetime.fromisoformat(loan_in.returned_at)
            if parsed_returned_at < loan.requested_at:
                raise ValidationError(detail="Returned at cannot be before requested at")
            loan.returned_at = parsed_returned_at
        
        if loan_in.rejected_at:
            parsed_rejected_at = datetime.fromisoformat(loan_in.rejected_at)
            if parsed_rejected_at < loan.requested_at:
                raise ValidationError(detail="Rejected at cannot be before requested at")
            loan.rejected_at = parsed_rejected_at

        if loan_in.status == "active" and loan.book.available_copies < 1:
            raise ValidationError(detail="No copies available")

        if loan_in.status:
            loan.status = loan_in.status
        if loan_in.rejection_reason:
            loan.rejection_reason = loan_in.rejection_reason

        if loan.status == "active":
            loan.book.available_copies -= 1
        elif loan.status == "returned":
            loan.book.available_copies += 1

        await self.db.commit()
        await self.db.refresh(loan)
        return loan

    async def request_loan(self, book_id: int, user: User) -> Loan | None:

        book_result = await self.db.execute(select(Book).where(Book.id == book_id))
        if not book_result.scalars().first():
            raise BookNotFound()

        stmt = (
            select(Loan)
            .where(Loan.book_id == book_id)
            .where(Loan.borrower_id == user.id)
            .where(Loan.status.in_(["active", "pending"]))
        )
        result = await self.db.execute(stmt)
        existing_loan = result.scalars().first() 

        if existing_loan:
            raise LoanAlreadyExists()

        new_loan = Loan(
            book_id=book_id,
            borrower_id=user.id,
            status="pending",
            requested_at=datetime.now(),
        )
        self.db.add(new_loan)
        await self.db.commit()
        result = await self.db.execute(
                select(Loan)
                .where(Loan.id == new_loan.id)
                .options(selectinload(Loan.book), selectinload(Loan.borrower))
            )
        return result.scalars().first()
        
    async def has_active_loan(self, borrower_id: uuid.UUID | str, book_id: int) -> bool:
        # Ensure borrower_id is UUID for comparison
        if isinstance(borrower_id, str):
            try:
                borrower_id = uuid.UUID(borrower_id)
            except ValueError:
                return False
        stmt = select(Loan).where(
            Loan.borrower_id == borrower_id,
            Loan.book_id == book_id,
            Loan.status == "active",
        )
        result = await self.db.execute(stmt)
        return result.scalars().first() is not None

    async def get_active_loans(self, user: User):
        stmt = select(Loan).where(Loan.borrower_id == user.id, Loan.status == "active")
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def return_loan(self, loan_id: int, user: User) -> Loan:
        loan = await self.get_by_id(loan_id, user)
        if loan.status != "active":
            raise LoanNotActive()
        
        if loan.borrower_id != user.id:
            raise WrongUser()
        
        loan.status = "returned"
        loan.returned_at = datetime.now()

        loan.book.available_copies += 1

        self.db.add(loan)
        await self.db.commit()
        await self.db.refresh(loan)
        await self.db.refresh(loan.book)
        return loan