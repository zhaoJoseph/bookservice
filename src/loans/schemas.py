from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Self
from uuid import UUID
from datetime import datetime

class BorrowerInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str

class BookInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    author: str
    isbn: str

class Loan(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    due_date: datetime | None
    returned_at: datetime | None
    approved_at: datetime | None
    rejection_reason: str | None
    requested_at: datetime
    rejected_at: datetime | None
    book: BookInfo
    borrower: BorrowerInfo

class LoanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    due_date: datetime | None
    returned_at: datetime | None
    approved_at: datetime | None
    rejection_reason: str | None
    requested_at: datetime
    rejected_at: datetime | None
    book: BookInfo
    borrower: BorrowerInfo

class LoanListQuery(BaseModel):
    title : str | None = None
    author : str | None = None
    isbn : str | None = None
    genre : str | None = None
    status : str | None = None
    page : int | None = 1
    limit : int | None = 20

class LoanListQueryAdmin(BaseModel):
    title : str | None = None
    author : str | None = None
    isbn : str | None = None
    genre : str | None = None
    id : str | None = None
    email : str | None = None
    status : str | None = None
    page : int | None = 1
    limit : int | None = 10

class LoanUpdate(BaseModel):
    status : str | None = None
    due_date : str | None = None
    returned_at : str | None = None
    approved_at : str | None = None
    rejected_at : str | None = None
    rejection_reason : str | None = None

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> Self:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided for update")
        return self
    
    @model_validator(mode="after")
    def status_consistency(self) -> Self:
        if self.status == "pending":
            if self.due_date or self.approved_at or self.returned_at or self.rejection_reason:
                raise ValueError("Pending loans cannot have resolution fields")
        if self.status == "active":
            if not (self.due_date and self.approved_at):
                raise ValueError("Active loans must have both due_date and approved_at")
        if self.status == "returned":
            if not self.returned_at:
                raise ValueError("Returned loans must have a returned_at")
        return self
    
    