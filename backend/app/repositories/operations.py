from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Expense, LedgerEntry, Supplier


class OperationsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_suppliers(self, business_id: UUID) -> list[Supplier]:
        rows = await self.session.scalars(
            select(Supplier).where(Supplier.business_id == business_id).order_by(Supplier.name)
        )
        return list(rows)

    async def list_expenses(
        self, business_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Expense]:
        rows = await self.session.scalars(
            select(Expense)
            .where(Expense.business_id == business_id)
            .order_by(Expense.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    async def list_ledger(
        self, business_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[LedgerEntry]:
        rows = await self.session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.business_id == business_id)
            .order_by(LedgerEntry.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows)
