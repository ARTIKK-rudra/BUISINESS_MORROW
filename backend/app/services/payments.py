from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.repositories.payments import PaymentsRepository


class PaymentsService:
    def __init__(self, session: AsyncSession):
        self.repository = PaymentsRepository(session)

    async def list(self, business_id: UUID, limit: int, offset: int) -> list[Payment]:
        return await self.repository.list(business_id, limit, offset)
