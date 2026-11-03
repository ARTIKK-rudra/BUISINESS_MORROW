from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.procurement import (
    GoodsReceiptCreate,
    GoodsReceiptRead,
    PurchaseCreate,
    PurchaseRead,
)
from app.services.authorization import Permission
from app.services.procurement import ProcurementService

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.get(
    "",
    response_model=list[PurchaseRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def list_purchases(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await ProcurementService(session).list_orders(membership.business_id, limit, offset)


@router.post(
    "",
    response_model=PurchaseRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def create_purchase(
    payload: PurchaseCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await ProcurementService(session).create_order(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.post(
    "/{purchase_id}/goods-received",
    response_model=GoodsReceiptRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def receive_goods(
    purchase_id: UUID,
    payload: GoodsReceiptCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await ProcurementService(session).receive(
        membership.business_id,
        principal.user_id,
        purchase_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/{purchase_id}/goods-received",
    response_model=list[GoodsReceiptRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def list_goods_receipts(purchase_id: UUID, membership: MembershipDep, session: SessionDep):
    return await ProcurementService(session).list_receipts(membership.business_id, purchase_id)
