from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=12, max_length=128)]
    business_name: str | None = Field(default=None, max_length=160)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserSummary(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    business_id: UUID
    user: UserSummary


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetAccepted(BaseModel):
    message: str = "If the account exists, reset instructions will be sent."
