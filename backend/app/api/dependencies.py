from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.models import BusinessMembership
from app.db.session import get_session
from app.repositories.auth import AuthRepository
from app.services.authorization import Permission, ensure_permission

bearer_scheme = HTTPBearer(auto_error=False)
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    business_id: UUID


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDep,
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("A bearer access token is required")
    user_id, business_id = decode_access_token(credentials.credentials)
    repository = AuthRepository(session)
    user = await repository.user_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User account is inactive or unavailable")
    membership = await repository.membership(user_id, business_id)
    if membership is None:
        raise ForbiddenError("No active membership for the requested business")
    return Principal(user_id=user_id, business_id=business_id)


async def get_current_membership(
    principal: Annotated[Principal, Depends(get_principal)], session: SessionDep
) -> BusinessMembership:
    membership = await AuthRepository(session).membership(principal.user_id, principal.business_id)
    if membership is None:
        raise ForbiddenError("No active membership for the requested business")
    return membership


def require_permission(permission: Permission) -> Callable:
    async def dependency(
        membership: Annotated[BusinessMembership, Depends(get_current_membership)],
    ) -> BusinessMembership:
        ensure_permission(membership.role, permission)
        return membership

    return dependency


PrincipalDep = Annotated[Principal, Depends(get_principal)]
MembershipDep = Annotated[BusinessMembership, Depends(get_current_membership)]
