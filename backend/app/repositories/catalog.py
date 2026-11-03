from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category, Product


class CatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_products(self, business_id: UUID) -> list[Product]:
        result = await self.session.scalars(
            select(Product)
            .where(Product.business_id == business_id, Product.is_active.is_(True))
            .order_by(Product.name)
        )
        return list(result)

    async def product_by_id(self, business_id: UUID, product_id: UUID) -> Product | None:
        return await self.session.scalar(
            select(Product).where(Product.business_id == business_id, Product.id == product_id)
        )

    async def sku_exists(self, business_id: UUID, sku: str) -> bool:
        return (
            await self.session.scalar(
                select(Product.id).where(Product.business_id == business_id, Product.sku == sku)
            )
            is not None
        )

    async def list_categories(self, business_id: UUID) -> list[Category]:
        result = await self.session.scalars(
            select(Category).where(Category.business_id == business_id).order_by(Category.name)
        )
        return list(result)

    async def category_by_id(self, business_id: UUID, category_id: UUID) -> Category | None:
        return await self.session.scalar(
            select(Category).where(Category.business_id == business_id, Category.id == category_id)
        )

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def commit(self) -> None:
        await self.session.commit()

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj: object) -> None:
        await self.session.refresh(obj)
