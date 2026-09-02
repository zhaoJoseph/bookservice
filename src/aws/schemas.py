from pydantic import BaseModel, EmailStr
from typing import Optional

class EmailRequest(BaseModel):
    to_email: EmailStr
    subject: str
    body: str
    cc_emails: Optional[list[EmailStr]] = None

class EmailResponse(BaseModel):
    message_id: str
    status: str = "sent"   