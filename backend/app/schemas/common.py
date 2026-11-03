from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: object | None = None


class Timestamped(ORMModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
