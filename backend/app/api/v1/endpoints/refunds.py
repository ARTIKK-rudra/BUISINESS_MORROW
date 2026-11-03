from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.procurement import RefundRead
from app.schemas.sales import RefundCreate
from app.services.authorization import Permission
from app.services.refunds import RefundService

router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.get(
    "",
    response_model=list[RefundRead],
    dependencies=[Depends(require_permission(Permission.SALES_READ))],
)
async def list_refunds(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await RefundService(session).list(membership.business_id, limit, offset)


@router.post(
    "",
    response_model=RefundRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.SALES_WRITE))],
)
async def create_refund(
    payload: RefundCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await RefundService(session).create(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )
