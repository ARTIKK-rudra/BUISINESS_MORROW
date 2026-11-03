from fastapi import APIRouter, Depends, Query

from app.api.dependencies import MembershipDep, SessionDep, require_permission
from app.core.errors import NotConfiguredError
from app.schemas.sales import PaymentRead
from app.services.authorization import Permission
from app.services.payments import PaymentsService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get(
    "",
    response_model=list[PaymentRead],
    dependencies=[Depends(require_permission(Permission.SALES_READ))],
)
async def list_payments(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await PaymentsService(session).list(membership.business_id, limit, offset)


@router.post(
    "", status_code=501, dependencies=[Depends(require_permission(Permission.SALES_WRITE))]
)
async def create_payment():
    raise NotConfiguredError("No payment provider is configured; no charge was attempted")
