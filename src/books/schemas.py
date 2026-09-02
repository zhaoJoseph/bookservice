from typing import Self, TypeVar, Generic, List
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Book(BaseModel):
    title: str = Field(..., min_length=3, max_length=1000)
    author: str = Field(..., min_length=3, max_length=1000)
    description: str = Field(..., min_length=3, max_length=25000)
    genre: str = Field(..., min_length=3, max_length=10000)
    cover_image_path: str | None = None
    total_copies: int = Field(..., ge=0)
    available_copies: int = Field(..., ge=0)
    isbn: str = Field(..., min_length=3, max_length=20)

class BookCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=1000)
    author: str = Field(..., min_length=3, max_length=1000)
    description: str = Field(..., min_length=3, max_length=25000)
    genre: str = Field(..., min_length=3, max_length=10000)
    cover_image_path: str | None = None
    total_copies: int = Field(..., ge=0)
    isbn: str = Field(..., min_length=3, max_length=20)

class BookUpdate(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=1000)
    author: str | None = Field(None, min_length=3, max_length=1000)
    description: str | None = Field(None, min_length=3, max_length=25000)
    genre: str | None = Field(None, min_length=3, max_length=10000)
    cover_image_path: str | None = None
    total_copies: int | None = Field(None, ge=0)
    isbn: str | None = Field(None, min_length=3, max_length=20)

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> Self:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided for update")
        return self

class BookListQuery(BaseModel):
    q : str | None = None
    genre : str | None = None
    available : bool | None = None
    page : int | None = 1
    limit : int | None = 20

class BookListQueryAdmin(BaseModel):
    q : str | None = None
    genre : str | None = None
    available : bool | None = None
    page : int | None = 1
    limit : int | None = 10

class BookPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str
    description: str
    genre: str
    cover_image_path: str | None = None
    total_copies: int
    available_copies: int
    isbn: str

# Generic pagination wrapper
T = TypeVar('T')

class PaginationResponse(BaseModel, Generic[T]):
    data: List[T]
    total: int
    page: int
    limit: int

# Specific response type
BookListResponse = PaginationResponse[BookPublic]