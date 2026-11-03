from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.db.models import InvoiceCapture
from app.schemas.assistant import OCRCaptureRead, OCRConfirm
from app.services.authorization import Permission
from app.services.ocr import MAX_IMAGE_BYTES, OCRService

router = APIRouter(prefix="/invoices", tags=["supplier invoices"])


@router.get(
    "/ocr-captures",
    response_model=list[OCRCaptureRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def list_ocr_captures(membership: MembershipDep, session: SessionDep):
    return list(
        await session.scalars(
            select(InvoiceCapture)
            .where(
                InvoiceCapture.business_id == membership.business_id,
                InvoiceCapture.status == "review_required",
            )
            .order_by(InvoiceCapture.created_at.desc())
            .limit(25)
        )
    )


@router.post(
    "/ocr-captures",
    response_model=OCRCaptureRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def create_ocr_capture(
    membership: MembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
    request: Request,
    file: Annotated[UploadFile, File()],
):
    content = await file.read(MAX_IMAGE_BYTES + 1)
    capture = await OCRService(session).capture(
        membership.business_id,
        principal.user_id,
        file.filename or "invoice",
        file.content_type or "",
        content,
        getattr(request.state, "request_id", None),
    )
    return capture


@router.post(
    "/ocr-captures/{capture_id}/confirm",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def confirm_ocr_capture(
    capture_id: UUID,
    payload: OCRConfirm,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    invoice = await OCRService(session).confirm(
        membership.business_id,
        capture_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )
    return {
        "id": invoice.id,
        "supplier_id": invoice.supplier_id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "currency": invoice.currency,
        "issued_at": invoice.issued_at,
    }


@router.post(
    "/ocr-captures/{capture_id}/reject",
    response_model=OCRCaptureRead,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def reject_ocr_capture(
    capture_id: UUID,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await OCRService(session).reject(
        membership.business_id,
        capture_id,
        principal.user_id,
        getattr(request.state, "request_id", None),
    )
