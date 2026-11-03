from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment


class PaymentsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, business_id: UUID, limit: int, offset: int) -> list[Payment]:
        result = await self.session.scalars(
            select(Payment)
            .where(Payment.business_id == business_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result)
