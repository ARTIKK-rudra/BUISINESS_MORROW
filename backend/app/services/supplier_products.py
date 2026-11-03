from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Ingredient,
    Product,
    Supplier,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.schemas.recipes import SupplierProductCreate, SupplierProductUpdate
from app.services.audit import add_audit_entry


class SupplierProductService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, business_id: UUID, supplier_id: UUID) -> list[SupplierProduct]:
        await self._supplier(business_id, supplier_id)
        return list(
            await self.session.scalars(
                select(SupplierProduct)
                .where(
                    SupplierProduct.business_id == business_id,
                    SupplierProduct.supplier_id == supplier_id,
                )
                .order_by(SupplierProduct.created_at.desc())
            )
        )

    async def create(
        self,
        business_id: UUID,
        supplier_id: UUID,
        actor_id: UUID,
        payload: SupplierProductCreate,
        request_id: str | None,
    ) -> SupplierProduct:
        await self._supplier(business_id, supplier_id)
        if payload.product_id:
            item = await self.session.scalar(
                select(Product).where(
                    Product.id == payload.product_id, Product.business_id == business_id
                )
            )
        else:
            item = await self.session.scalar(
                select(Ingredient).where(
                    Ingredient.id == payload.ingredient_id,
                    Ingredient.business_id == business_id,
                )
            )
        if item is None:
            raise NotFoundError("Product or ingredient not found")
        link = SupplierProduct(
            business_id=business_id,
            supplier_id=supplier_id,
            product_id=payload.product_id,
            ingredient_id=payload.ingredient_id,
            unit_cost=payload.unit_cost,
            currency=payload.currency,
            lead_time_days=payload.lead_time_days,
            minimum_order_quantity=payload.minimum_order_quantity,
        )
        self.session.add(link)
        try:
            await self.session.flush()
            self.session.add(
                SupplierPriceHistory(
                    supplier_product_id=link.id,
                    unit_cost=link.unit_cost,
                    currency=link.currency,
                )
            )
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="supplier_product.created",
                entity_type="supplier_product",
                entity_id=link.id,
                request_id=request_id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Supplier already has this stock item in its catalog") from exc
        await self.session.refresh(link)
        return link

    async def update(
        self,
        business_id: UUID,
        supplier_id: UUID,
        link_id: UUID,
        actor_id: UUID,
        payload: SupplierProductUpdate,
        request_id: str | None,
    ) -> SupplierProduct:
        link = await self.session.scalar(
            select(SupplierProduct).where(
                SupplierProduct.id == link_id,
                SupplierProduct.business_id == business_id,
                SupplierProduct.supplier_id == supplier_id,
            )
        )
        if link is None:
            raise NotFoundError("Supplier product not found")
        link.unit_cost = payload.unit_cost
        link.currency = payload.currency
        link.lead_time_days = payload.lead_time_days
        link.minimum_order_quantity = payload.minimum_order_quantity
        self.session.add(
            SupplierPriceHistory(
                supplier_product_id=link.id,
                unit_cost=link.unit_cost,
                currency=link.currency,
            )
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="supplier_product.price_updated",
            entity_type="supplier_product",
            entity_id=link.id,
            request_id=request_id,
            metadata={"unit_cost": str(link.unit_cost), "currency": link.currency},
        )
        await self.session.commit()
        await self.session.refresh(link)
        return link

    async def price_history(
        self, business_id: UUID, supplier_id: UUID, link_id: UUID
    ) -> list[SupplierPriceHistory]:
        link = await self.session.scalar(
            select(SupplierProduct.id).where(
                SupplierProduct.id == link_id,
                SupplierProduct.business_id == business_id,
                SupplierProduct.supplier_id == supplier_id,
            )
        )
        if link is None:
            raise NotFoundError("Supplier product not found")
        return list(
            await self.session.scalars(
                select(SupplierPriceHistory)
                .where(SupplierPriceHistory.supplier_product_id == link_id)
                .order_by(SupplierPriceHistory.effective_at.desc())
            )
        )

    async def _supplier(self, business_id: UUID, supplier_id: UUID) -> Supplier:
        supplier = await self.session.scalar(
            select(Supplier).where(Supplier.id == supplier_id, Supplier.business_id == business_id)
        )
        if supplier is None:
            raise NotFoundError("Supplier not found")
        return supplier
