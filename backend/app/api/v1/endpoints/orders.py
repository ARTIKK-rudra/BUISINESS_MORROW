from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.sales import OrderCreate, OrderRead
from app.services.authorization import Permission
from app.services.sales import SalesService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get(
    "",
    response_model=list[OrderRead],
    dependencies=[Depends(require_permission(Permission.SALES_READ))],
)
async def list_orders(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await SalesService(session).list_orders(membership.business_id, limit, offset)


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.SALES_WRITE))],
)
async def create_order(
    payload: OrderCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await SalesService(session).create_order(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )
