# src/books/service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_, and_, literal
from .models import Book
from ..models import User
from ..loans.models import Loan
from .schemas import BookCreate, BookUpdate, BookListQuery, BookListQueryAdmin
from .exceptions import BookNotFound, ISBNRequired, ISBNAlreadyExists, FailedDelete
from typing import Sequence, Tuple

class BookService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, book_id: int) -> Book:
        result = await self.db.execute(select(Book).where(Book.id == book_id))
        book = result.scalars().first()
        if not book:
            raise BookNotFound()
        return book

    async def list_books(self, query: BookListQuery | BookListQueryAdmin, 
                         admin: bool = False, user: User | None = None) -> Tuple[Sequence[Book], int]:
        if user:
            stmt = (
                select(Book, Loan.id)
                .outerjoin(
                    Loan,
                    and_(
                        Loan.book_id == Book.id,
                        Loan.borrower_id == user.id,
                        Loan.status.in_(["active", "pending"]),
                    ),
                )
            )
        else:
            stmt = select(Book, literal(None).label("loan_id"))

        if query.q:
            stmt = stmt.where(or_(
                Book.title.ilike(f"%{query.q}%"),
                Book.author.ilike(f"%{query.q}%")
            ))
        if query.genre:
            stmt = stmt.where(Book.genre == query.genre)
        if query.available:
            stmt = stmt.where(Book.available_copies > 0)

        # Count total matching rows BEFORE pagination is applied
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt) or 0

        # Now apply pagination to fetch just this page's rows
        limit = query.limit or (10 if admin else 20)
        if query.page:
            offset = (query.page - 1) * limit
        else:
            offset = 0
        stmt = stmt.offset(offset).limit(limit).order_by(Book.title)

        result = await self.db.execute(stmt)
        rows = result.all()  

        books = []
        for book, loan_id in rows:
            book.loan_id = loan_id
            books.append(book)

        return books, total

    async def create_book(self, book_in: BookCreate) -> Book:
        if not book_in.isbn:
            raise ISBNRequired()
        
        # Check ISBN existence
        result = await self.db.execute(select(Book).where(Book.isbn == book_in.isbn))
        if result.scalars().first():
            raise ISBNAlreadyExists()
        
        new_book = Book(
            **book_in.model_dump(),
            available_copies=book_in.total_copies
        )
        self.db.add(new_book)
        await self.db.commit()
        await self.db.refresh(new_book)
        return new_book

    async def update_book(self, book_id: int, book_in: BookUpdate) -> Book:
        book = await self.get_by_id(book_id) # Reuses not found check
        
        if book_in.isbn and book_in.isbn != book.isbn:
            result = await self.db.execute(select(Book).where(Book.isbn == book_in.isbn))
            if result.scalars().first():
                raise ISBNAlreadyExists()
        
        # TODO: Add loan check logic here before updating total_copies
        
        update_data = book_in.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in update_data.items():
            setattr(book, field, value)
            
        await self.db.commit()
        await self.db.refresh(book)
        return book

    async def delete_book(self, book_id: int) -> None:
        book = await self.get_by_id(book_id)
        
        # TODO: Check active loans before deleting
        # if book.active_loans > 0: raise FailedDelete()

        if not book:
            raise BookNotFound()
        try:
            await self.db.execute(delete(Book).where(Book.id == book_id))
            await self.db.commit()
        except Exception:
            raise FailedDelete()   