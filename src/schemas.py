import uuid
from enum import Enum

from datetime import datetime

from typing import Optional

from fastapi_users import schemas as fu_schemas
from pydantic import BaseModel, Field, ConfigDict


class Role(str, Enum):
    admin = "admin"
    user = "user"

class Status(str, Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"

class UserRead(fu_schemas.BaseUser[uuid.UUID]):
    name: str
    role: Role
    status: Status

class UserCreate(fu_schemas.BaseUserCreate):
    name: str = Field(..., min_length=3, max_length=20)
    role: Role = Role.user
    token : str | None = None
    status: Status | None = None
    model_config = ConfigDict(populate_by_name=True)
    genres: str = Field(..., min_length=3, max_length=150)

class UserUpdate(fu_schemas.BaseUserUpdate):
    name: Optional[str] = Field(default=None, min_length=3, max_length=20)
    role: Optional[Role] = None
    status: Optional[str] = None
    verified_at: Optional[datetime] = None
    token: Optional[str] = None

class Token(BaseModel):
    accessToken: str
    tokenType: str
