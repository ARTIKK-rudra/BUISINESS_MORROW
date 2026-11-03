from fastapi import APIRouter, Depends, Query

from app.api.dependencies import MembershipDep, SessionDep, require_permission
from app.schemas.finance import LedgerEntryRead
from app.services.authorization import Permission
from app.services.operations import OperationsService

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get(
    "",
    response_model=list[LedgerEntryRead],
    dependencies=[Depends(require_permission(Permission.FINANCE_READ))],
)
async def list_ledger(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await OperationsService(session).list_ledger(membership.business_id, limit, offset)
