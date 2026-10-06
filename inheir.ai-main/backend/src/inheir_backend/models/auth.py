from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
import re
from typing import Literal

class SignUpRequest(BaseModel):
    model_config = ConfigDict(str_min_length=1)
    username: str
    full_name: str
    email: EmailStr
    password: str
    role: Literal["User", "Admin", "Guest", "Moderator"] = "User"

    @field_validator('username')
    def validate_username(cls, value):
        if not re.match(r"^\w+$", value):
            raise ValueError(
                'Username must have only alphabets, digits and underscores')
        return value

    @field_validator('full_name')
    def validate_full_name(cls, value):
        if not re.match("^([A-Za-z ])+$", value):
            raise ValueError(
                'Full name must have only alphabets, digits and underscores')
        return value.title()

    @field_validator('password')
    def validate_password(cls, value):
        if len(value) < 8 or len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at least 8 characters and at most 72 UTF-8 bytes')
        return value

class SignInRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    token: str | None
