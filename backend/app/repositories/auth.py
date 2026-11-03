from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Business, BusinessMembership, User


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def user_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def membership(self, user_id: UUID, business_id: UUID) -> BusinessMembership | None:
        return await self.session.scalar(
            select(BusinessMembership)
            .join(Business, Business.id == BusinessMembership.business_id)
            .where(
                BusinessMembership.user_id == user_id,
                BusinessMembership.business_id == business_id,
                BusinessMembership.is_active.is_(True),
                Business.is_active.is_(True),
            )
        )

    async def first_membership(self, user_id: UUID) -> BusinessMembership | None:
        return await self.session.scalar(
            select(BusinessMembership)
            .join(Business, Business.id == BusinessMembership.business_id)
            .where(
                BusinessMembership.user_id == user_id,
                BusinessMembership.is_active.is_(True),
                Business.is_active.is_(True),
            )
            .order_by(BusinessMembership.created_at)
            .limit(1)
        )

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def businesses_for_user(self, user_id: UUID) -> list[Business]:
        result = await self.session.scalars(
            select(Business)
            .join(BusinessMembership, BusinessMembership.business_id == Business.id)
            .where(BusinessMembership.user_id == user_id, BusinessMembership.is_active.is_(True))
            .order_by(Business.name)
        )
        return list(result)
