from pydantic import BaseModel, Field, EmailStr, field_validator, ValidationInfo
import ast
import re

class UserForm(BaseModel):
    """Strict schema: matches exactly what the HTML form sends"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str
    name: str = Field(..., min_length=3, pattern=r"^[a-zA-Z\s]+$")
    genres: list[int] = Field(default_factory=list)

    @field_validator('genres', mode='before')
    @classmethod
    def parse_genres(cls, v):
        # HTML forms send repeated fields (genres=1&genres=2&...), but a single
        # stringified list like "[1,2,3]" also arrives as a one-item list.
        if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str) and v[0].strip().startswith('['):
            try:
                v = ast.literal_eval(v[0])
            except (ValueError, SyntaxError):
                raise ValueError("Invalid genres format")
        return v

    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[@$!%*?&]", v):
            raise ValueError("Password must contain at least one special character (@$!%*?&)")
        return v
    
    @field_validator('confirm_password')
    @classmethod
    def validate_password_match(cls, v: str, info: ValidationInfo) -> str:
        if 'password' in info.data and v != info.data['password']:
            raise ValueError("Passwords do not match")
        return v