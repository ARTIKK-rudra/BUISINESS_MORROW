from pydantic import EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotConfiguredError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Business, BusinessMembership, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserSummary
from app.services.audit import add_audit_entry


def normalize_email(email: str | EmailStr) -> str:
    return str(email).strip().lower()


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AuthRepository(session)

    async def register(
        self, payload: RegisterRequest, request_id: str | None = None
    ) -> TokenResponse:
        email = normalize_email(payload.email)
        if await self.repository.user_by_email(email):
            raise ConflictError("An account with this email already exists")
        user = User(
            email=email,
            full_name=payload.name.strip(),
            password_hash=hash_password(payload.password),
        )
        business = Business(
            name=(payload.business_name or f"{payload.name.strip()}'s business").strip()
        )
        self.repository.add(user)
        self.repository.add(business)
        await self.repository.flush()
        membership = BusinessMembership(business_id=business.id, user_id=user.id, role="owner")
        self.repository.add(membership)
        add_audit_entry(
            self.session,
            business_id=business.id,
            actor_user_id=user.id,
            action="business.registered",
            entity_type="business",
            entity_id=business.id,
            request_id=request_id,
        )
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictError("An account with this email already exists") from exc
        return TokenResponse(
            access_token=create_access_token(user.id, business.id),
            business_id=business.id,
            user=UserSummary(id=user.id, full_name=user.full_name, email=user.email),
        )

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.repository.user_by_email(normalize_email(payload.email))
        if (
            not user
            or not user.is_active
            or not verify_password(payload.password, user.password_hash)
        ):
            raise UnauthorizedError("Email or password is incorrect")
        membership = await self.repository.first_membership(user.id)
        if membership is None:
            raise UnauthorizedError("This account does not have an active business membership")
        return TokenResponse(
            access_token=create_access_token(user.id, membership.business_id),
            business_id=membership.business_id,
            user=UserSummary(id=user.id, full_name=user.full_name, email=user.email),
        )


async def accept_password_reset_request(_email: str) -> None:
    raise NotConfiguredError(
        "Password reset email is unavailable until an email provider is configured"
    )
