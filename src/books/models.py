from ..database import Base

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship, Mapped, DeclarativeBase, mapped_column

from datetime import datetime

class Book(Base):
    __tablename__ = "books"

    __table_args__ = (
        CheckConstraint(
            "available_copies <= total_copies",
            name="ck_available_copies_le_total_copies",
        ),
        CheckConstraint(
            "total_copies >= 0",
            name="ck_total_copies_ge_zero",
        ),
        CheckConstraint(
            "available_copies >= 0",
            name="ck_available_copies_ge_zero",
        ),
    )

    id : Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title : Mapped[str] = mapped_column(String(1000), nullable=False)
    author : Mapped[str] = mapped_column(String(1000), nullable=False)
    description : Mapped[str] = mapped_column(String(25000), nullable=False)
    genre : Mapped[str] = mapped_column(String(10000), nullable=False)
    cover_image_path : Mapped[str] = mapped_column(String(200), nullable=True)
    total_copies : Mapped[int] = mapped_column(Integer, nullable=False)
    available_copies : Mapped[int] = mapped_column(Integer, nullable=False)
    createdAt : Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    updatedAt : Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    isbn : Mapped[str] = mapped_column(String(20) or String(13), unique=True, nullable=False)