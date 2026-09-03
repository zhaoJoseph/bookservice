from ..database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column

from sqlalchemy import String
from fastapi_users_db_sqlalchemy.generics import GUID
import uuid

from ..books.models import Book
from ..models import User

from datetime import datetime

class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint(
            "status != 'pending' OR (due_date IS NULL AND approved_at IS NULL "
            "AND returned_at IS NULL AND rejection_reason IS NULL)",
            name="ck_pending_loan_has_no_resolution_fields",
        ),
        CheckConstraint(
            "due_date IS NULL OR due_date >= requested_at",
            name="ck_due_date_after_requested_at",
        ),
        CheckConstraint(
            "approved_at IS NULL OR approved_at >= requested_at",
            name="ck_approved_at_after_requested_at",
        ),
        CheckConstraint(
            "returned_at IS NULL OR returned_at >= requested_at",
            name="ck_returned_at_after_requested_at",
        ),
    )

    id : Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Use UUID type for borrower_id to match users.id (UUID)
    borrower_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id"))
    book_id : Mapped[int] = mapped_column(Integer, ForeignKey("books.id"))
    status : Mapped[str] = mapped_column(String(20), nullable=False)
    rejection_reason : Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_date : Mapped[datetime] = mapped_column(DateTime, nullable=True)
    returned_at : Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requested_at : Mapped[datetime] = mapped_column(DateTime, nullable=False)
    approved_at : Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at : Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    book: Mapped["Book"] = relationship("Book", lazy="selectin")
    borrower: Mapped["User"] = relationship("User", lazy="selectin")