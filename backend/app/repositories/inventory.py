from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Inventory, InventoryMovement


class InventoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_inventory_records(self, business_id: UUID) -> list[Inventory]:
        result = await self.session.scalars(
            select(Inventory)
            .where(Inventory.business_id == business_id)
            .order_by(Inventory.location)
        )
        return list(result)

    async def get_for_update(self, business_id: UUID, inventory_id: UUID) -> Inventory | None:
        return await self.session.scalar(
            select(Inventory)
            .where(Inventory.business_id == business_id, Inventory.id == inventory_id)
            .with_for_update()
        )

    async def movement_history(
        self, business_id: UUID, inventory_id: UUID
    ) -> list[InventoryMovement]:
        result = await self.session.scalars(
            select(InventoryMovement)
            .where(
                InventoryMovement.business_id == business_id,
                InventoryMovement.inventory_id == inventory_id,
            )
            .order_by(InventoryMovement.created_at.desc())
            .limit(100)
        )
        return list(result)

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()
