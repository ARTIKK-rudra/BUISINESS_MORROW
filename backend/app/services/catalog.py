from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Category, Product
from app.repositories.catalog import CatalogRepository
from app.schemas.catalog import CategoryCreate, ProductCreate
from app.services.audit import add_audit_entry


class CatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = CatalogRepository(session)

    async def list_products(self, business_id: UUID) -> list[Product]:
        return await self.repository.list_products(business_id)

    async def create_product(
        self, business_id: UUID, actor_id: UUID, payload: ProductCreate, request_id: str | None
    ) -> Product:
        sku = payload.sku.strip()
        if await self.repository.sku_exists(business_id, sku):
            raise ConflictError("A product with this SKU already exists")
        if payload.category_id:
            category_ids = {c.id for c in await self.repository.list_categories(business_id)}
            if payload.category_id not in category_ids:
                raise NotFoundError("Category not found")
        product = Product(
            business_id=business_id,
            sku=sku,
            name=payload.name.strip(),
            description=payload.description,
            category_id=payload.category_id,
            price=payload.price,
            unit=payload.unit.strip(),
        )
        self.repository.add(product)
        try:
            await self.repository.flush()
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="product.created",
                entity_type="product",
                entity_id=product.id,
                request_id=request_id,
                metadata={"sku": sku},
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A product with this SKU already exists") from exc
        await self.repository.refresh(product)
        return product

    async def list_categories(self, business_id: UUID) -> list[Category]:
        return await self.repository.list_categories(business_id)

    async def create_category(
        self, business_id: UUID, actor_id: UUID, payload: CategoryCreate, request_id: str | None
    ) -> Category:
        if (
            payload.parent_id
            and await self.repository.category_by_id(business_id, payload.parent_id) is None
        ):
            raise NotFoundError("Parent category not found")
        category = Category(
            business_id=business_id,
            name=payload.name.strip(),
            description=payload.description,
            parent_id=payload.parent_id,
        )
        self.repository.add(category)
        try:
            await self.repository.flush()
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="category.created",
                entity_type="category",
                entity_id=category.id,
                request_id=request_id,
            )
            await self.repository.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Category already exists or parent is invalid") from exc
        await self.repository.refresh(category)
        return category
