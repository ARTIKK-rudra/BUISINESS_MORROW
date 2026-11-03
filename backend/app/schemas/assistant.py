from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    current_route: str | None = Field(default=None, max_length=120, pattern=r"^/[a-z0-9-]*$")
    conversation_history: list[str] = Field(default_factory=list, max_length=6)


class VoiceQuestion(AssistantQuestion):
    consent_to_store_transcript: bool = False
    conversation_session: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class AssistantAnswer(BaseModel):
    answer: str
    intent: str
    sources: list[str]
    generated_at: datetime
    grounded: bool = True
    navigation_path: str | None = None


class OCRCaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    ocr_engine: str
    raw_text: str
    draft: dict
    review_required: bool = True


class OCRConfirm(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=80)
    supplier_id: UUID
    subtotal: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    tax: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern="^[A-Z]{3}$")
    issued_at: datetime | None = None
    items: list["OCRLineItem"] = Field(default_factory=list, max_length=100)


class OCRLineItem(BaseModel):
    description: str = Field(min_length=1, max_length=240)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class ReorderPreview(BaseModel):
    recommendation_id: UUID
    item_name: str
    quantity: Decimal
    unit: str
    supplier_id: UUID
    supplier_name: str
    supplier_product_id: UUID
    unit_cost: Decimal
    estimated_total: Decimal
    currency: str
    recommended_date: date | None = None


class ReorderApproval(BaseModel):
    supplier_product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_cost: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
