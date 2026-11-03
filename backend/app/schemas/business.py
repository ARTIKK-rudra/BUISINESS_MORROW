from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped


class BusinessRead(Timestamped):
    name: str
    timezone: str
    base_currency: str
    is_active: bool


class UserRead(Timestamped):
    email: str
    full_name: str
    is_active: bool


class UserInvite(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=160)
    role: str = Field(pattern="^(manager|staff|analyst)$")


class MembershipRead(BaseModel):
    id: UUID
    business_id: UUID
    user_id: UUID
    role: str
    is_active: bool
