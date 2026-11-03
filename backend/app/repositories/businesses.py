from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Business, BusinessMembership


class BusinessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_member(self, user_id: UUID, business_id: UUID) -> Business | None:
        return await self.session.scalar(
            select(Business)
            .join(BusinessMembership, BusinessMembership.business_id == Business.id)
            .where(
                Business.id == business_id,
                BusinessMembership.user_id == user_id,
                BusinessMembership.is_active.is_(True),
            )
        )

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def commit(self) -> None:
        await self.session.commit()

    async def refresh(self, obj: object) -> None:
        await self.session.refresh(obj)
