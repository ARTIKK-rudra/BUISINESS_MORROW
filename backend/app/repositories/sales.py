from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Order


class SalesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_orders(
        self, business_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Order]:
        result = await self.session.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.business_id == business_id)
            .order_by(Order.placed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def order_by_idempotency(self, business_id: UUID, key: str) -> Order | None:
        return await self.session.scalar(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.business_id == business_id, Order.idempotency_key == key)
        )
