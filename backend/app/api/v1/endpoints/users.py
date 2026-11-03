from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.core.errors import NotConfiguredError, UnauthorizedError
from app.db.models import BusinessMembership, User
from app.schemas.business import UserRead
from app.services.authorization import Permission

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def current_user(principal: PrincipalDep, session: SessionDep):
    user = await session.get(User, principal.user_id)
    if user is None:
        raise UnauthorizedError("User account is unavailable")
    return user


@router.get(
    "",
    response_model=list[UserRead],
    dependencies=[Depends(require_permission(Permission.USERS_READ))],
)
async def list_business_users(membership: MembershipDep, session: SessionDep):
    result = await session.scalars(
        select(User)
        .join(BusinessMembership, BusinessMembership.user_id == User.id)
        .where(
            BusinessMembership.business_id == membership.business_id,
            BusinessMembership.is_active.is_(True),
        )
        .order_by(User.full_name)
    )
    return list(result)


@router.post(
    "/invitations",
    status_code=501,
    dependencies=[Depends(require_permission(Permission.USERS_WRITE))],
)
async def invite_user():
    raise NotConfiguredError(
        "Invitations require an email delivery provider, which is not configured"
    )
