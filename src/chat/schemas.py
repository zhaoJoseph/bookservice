from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID

class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str

class Chat(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    content: str | None = None
    user: UserInfo

class MessageRequest(BaseModel):
    message : str