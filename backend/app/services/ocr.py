from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotConfiguredError, NotFoundError
from app.db.models import Invoice, InvoiceCapture, InvoiceLine, Supplier
from app.schemas.assistant import OCRConfirm
from app.services.audit import add_audit_entry

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/webp"}
MIME_FORMATS = {
    "image/jpeg": {"JPEG"},
    "image/png": {"PNG"},
    "image/tiff": {"TIFF"},
    "image/webp": {"WEBP"},
}
TESSERACT_TIMEOUT_SECONDS = 20


def extract_fields(raw_text: str) -> tuple[dict, float]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    invoice_match = re.search(
        r"(?:invoice|inv|bill)\s*(?:no|number|#|:)?\s*[:#-]?\s*([A-Z0-9/-]{3,})", raw_text, re.I
    )
    date_match = re.search(
        r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b", raw_text
    )
    currency_match = re.search(r"\b(USD|EUR|GBP|INR|CAD|AUD|JPY)\b|[₹€£$]", raw_text, re.I)
    currency_map = {"₹": "INR", "€": "EUR", "£": "GBP", "$": "USD"}
    currency = (
        (
            currency_match.group(1).upper()
            if currency_match and currency_match.group(1)
            else currency_map.get(currency_match.group(0), "")
        )
        if currency_match
        else ""
    )
    amount_pattern = (
        r"(?:total\s*(?:due)?|grand\s*total|amount\s*due)\s*[: ]*\s*"
        r"(?:[₹€£$]|(?:USD|EUR|GBP|INR)\s*)?([\d,]+\.\d{2})"
    )
    total_match = re.search(amount_pattern, raw_text, re.I)
    subtotal_match = re.search(r"subtotal\s*[: ]*\s*(?:[₹€£$])?([\d,]+\.\d{2})", raw_text, re.I)
    tax_match = re.search(r"(?:tax|VAT|GST)\s*[: ]*\s*(?:[₹€£$])?([\d,]+\.\d{2})", raw_text, re.I)

    def decimal_match(match):
        try:
            return str(Decimal(match.group(1).replace(",", ""))) if match else ""
        except InvalidOperation:
            return ""

    date_value = date_match.group(1) if date_match else ""
    lines_out = []
    for line in lines:
        match = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s+(?:[₹€£$])?([\d,]+\.\d{2})\s*$", line)
        if match and not re.search(r"total|subtotal|tax|invoice|date", line, re.I):
            lines_out.append(
                {
                    "description": match.group(1),
                    "quantity": match.group(2),
                    "unit_price": match.group(3).replace(",", ""),
                }
            )
    fields = [
        bool(invoice_match),
        bool(date_match),
        bool(total_match),
        bool(currency_match),
        bool(lines_out),
    ]
    confidence = round(sum(fields) / len(fields), 2)
    return {
        "supplier_name": lines[0][:180] if lines else "",
        "invoice_number": invoice_match.group(1) if invoice_match else "",
        "issued_date": date_value,
        "currency": currency,
        "subtotal": decimal_match(subtotal_match),
        "tax": decimal_match(tax_match),
        "total": decimal_match(total_match),
        "items": lines_out,
        "field_confidence": confidence,
        "needs_manual_review": True,
    }, confidence


class OCRService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def capture(
        self,
        business_id: UUID,
        user_id: UUID,
        filename: str,
        media_type: str,
        content: bytes,
        request_id: str | None = None,
    ) -> InvoiceCapture:
        if media_type not in ALLOWED_IMAGE_TYPES or len(content) > MAX_IMAGE_BYTES:
            raise ConflictError("Upload a JPEG, PNG, TIFF, or WebP image smaller than 10 MB")
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in MIME_FORMATS[media_type]:
                    raise ConflictError(
                        "Uploaded image content does not match its declared file type"
                    )
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ConflictError("Image dimensions exceed the 25 megapixel limit")
                image = ImageOps.exif_transpose(image).convert("RGB")
                raw_text = pytesseract.image_to_string(
                    image, config="--psm 6", timeout=TESSERACT_TIMEOUT_SECONDS
                )
        except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
            raise NotConfiguredError(
                "OCR requires the Tesseract engine. Install it or run the Docker image."
            ) from exc
        except RuntimeError as exc:
            raise ConflictError(
                "OCR processing exceeded its time limit; use a smaller image"
            ) from exc
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
            raise ConflictError("The uploaded file is not a readable image") from exc
        if not raw_text.strip():
            raise ConflictError("No readable text was found; try a clearer invoice image")
        draft, _ = extract_fields(raw_text)
        capture = InvoiceCapture(
            business_id=business_id,
            uploaded_by=user_id,
            status="review_required",
            ocr_engine=f"tesseract-{pytesseract.get_tesseract_version()}",
            raw_text=raw_text[:20000],
            draft=draft,
        )
        self.session.add(capture)
        await self.session.flush()
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=user_id,
            action="invoice.ocr_capture_created",
            entity_type="invoice_capture",
            entity_id=capture.id,
            request_id=request_id,
            metadata={"ocr_engine": capture.ocr_engine},
        )
        await self.session.commit()
        await self.session.refresh(capture)
        return capture

    async def confirm(
        self,
        business_id: UUID,
        capture_id: UUID,
        actor_id: UUID,
        payload: OCRConfirm,
        request_id: str | None,
    ):
        capture = await self.session.scalar(
            select(InvoiceCapture)
            .where(InvoiceCapture.id == capture_id, InvoiceCapture.business_id == business_id)
            .with_for_update()
        )
        if capture is None:
            raise NotFoundError("Invoice capture not found")
        if capture.status != "review_required":
            raise ConflictError("This invoice capture has already been reviewed")
        supplier = await self.session.scalar(
            select(Supplier).where(
                Supplier.id == payload.supplier_id,
                Supplier.business_id == business_id,
                Supplier.is_active.is_(True),
            )
        )
        if supplier is None:
            raise NotFoundError("Active supplier not found in this business")
        if payload.total != payload.subtotal + payload.tax:
            raise ConflictError("Invoice total must equal subtotal plus tax")
        if payload.items:
            line_total = sum(
                (item.quantity * item.unit_price for item in payload.items), Decimal(0)
            )
            if abs(line_total - payload.subtotal) > Decimal("0.01"):
                raise ConflictError("Verified invoice line totals must match the subtotal")
        invoice_number = payload.invoice_number.strip()
        if not invoice_number:
            raise ConflictError("Invoice number cannot be blank")
        duplicate = await self.session.scalar(
            select(Invoice).where(
                Invoice.business_id == business_id, Invoice.invoice_number == invoice_number
            )
        )
        if duplicate:
            raise ConflictError("An invoice with this number already exists")
        invoice = Invoice(
            business_id=business_id,
            supplier_id=supplier.id,
            invoice_number=invoice_number,
            status="received",
            subtotal=payload.subtotal,
            tax=payload.tax,
            total=payload.total,
            currency=payload.currency,
            issued_at=payload.issued_at or datetime.now(UTC),
        )
        self.session.add(invoice)
        await self.session.flush()
        self.session.add_all(
            [
                InvoiceLine(
                    invoice_id=invoice.id,
                    description=item.description.strip(),
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
                for item in payload.items
            ]
        )
        capture.status = "confirmed"
        capture.confirmed_by = actor_id
        capture.confirmed_at = datetime.now(UTC)
        capture.invoice_id = invoice.id
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="invoice.ocr_confirmed",
            entity_type="invoice",
            entity_id=invoice.id,
            request_id=request_id,
            metadata={"capture_id": str(capture.id), "supplier_id": str(supplier.id)},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("An invoice with this number already exists") from exc
        await self.session.refresh(invoice)
        return invoice

    async def reject(
        self,
        business_id: UUID,
        capture_id: UUID,
        actor_id: UUID,
        request_id: str | None,
    ) -> InvoiceCapture:
        capture = await self.session.scalar(
            select(InvoiceCapture)
            .where(
                InvoiceCapture.id == capture_id,
                InvoiceCapture.business_id == business_id,
            )
            .with_for_update()
        )
        if capture is None:
            raise NotFoundError("Invoice capture not found")
        if capture.status != "review_required":
            raise ConflictError("This invoice capture has already been reviewed")
        capture.status = "rejected"
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="invoice.ocr_capture_rejected",
            entity_type="invoice_capture",
            entity_id=capture.id,
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(capture)
        return capture
