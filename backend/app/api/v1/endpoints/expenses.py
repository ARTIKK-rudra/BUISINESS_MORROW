from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.finance import ExpenseCreate, ExpenseRead
from app.services.authorization import Permission
from app.services.operations import OperationsService

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get(
    "",
    response_model=list[ExpenseRead],
    dependencies=[Depends(require_permission(Permission.FINANCE_READ))],
)
async def list_expenses(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await OperationsService(session).list_expenses(membership.business_id, limit, offset)


@router.post(
    "",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.FINANCE_WRITE))],
)
async def create_expense(
    payload: ExpenseCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await OperationsService(session).create_expense(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )
