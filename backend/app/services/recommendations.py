from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Business,
    Ingredient,
    Inventory,
    Product,
    Purchase,
    PurchaseItem,
    Recommendation,
    Supplier,
    SupplierProduct,
)
from app.schemas.assistant import ReorderApproval
from app.schemas.procurement import PurchaseCreate, PurchaseItemCreate
from app.services.audit import add_audit_entry
from app.services.procurement import ProcurementService


class RecommendationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _outstanding_quantity(self, business_id: UUID, stock: Inventory) -> Decimal:
        query = (
            select(func.sum(PurchaseItem.quantity - PurchaseItem.received_quantity))
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .where(
                Purchase.business_id == business_id,
                Purchase.status.in_({"ordered", "partially_received"}),
            )
        )
        if stock.product_id:
            query = query.where(PurchaseItem.product_id == stock.product_id)
        else:
            query = query.where(PurchaseItem.ingredient_id == stock.ingredient_id)
        return Decimal(await self.session.scalar(query) or 0)

    async def preview_reorder(self, business_id: UUID, recommendation_id: UUID) -> dict:
        recommendation = await self.session.scalar(
            select(Recommendation).where(
                Recommendation.id == recommendation_id,
                Recommendation.business_id == business_id,
            )
        )
        if recommendation is None:
            raise NotFoundError("Recommendation not found")
        if recommendation.status != "pending" or recommendation.recommendation_type != "reorder":
            raise ConflictError("Only pending reorder recommendations can be previewed")
        try:
            inventory_id = UUID(recommendation.target_id)
        except ValueError as exc:
            raise ConflictError("Recommendation inventory reference is invalid") from exc
        stock = await self.session.scalar(
            select(Inventory).where(
                Inventory.id == inventory_id,
                Inventory.business_id == business_id,
            )
        )
        if stock is None:
            raise NotFoundError("Recommended inventory item no longer exists")
        forecast_reorder = (recommendation.provenance or {}).get(
            "source"
        ) == "forecast_reorder_engine"
        if forecast_reorder:
            quantity = Decimal(str(recommendation.provenance["recommended_quantity"]))
            if quantity <= 0 or Decimal(stock.quantity) != Decimal(
                str(recommendation.provenance["inventory_on_hand"])
            ):
                raise ConflictError(
                    "Inventory changed; regenerate the recommendation before review"
                )
            outstanding = await self._outstanding_quantity(business_id, stock)
            if outstanding != Decimal(
                str(recommendation.provenance["outstanding_purchase_quantity"])
            ):
                raise ConflictError(
                    "Open purchase orders changed; regenerate the recommendation before review"
                )
        else:
            quantity = max(stock.reorder_point + stock.safety_stock - stock.quantity, Decimal(0))
            quantity = max(
                quantity - await self._outstanding_quantity(business_id, stock), Decimal(0)
            )
            if quantity <= 0:
                raise ConflictError(
                    "Current stock and outstanding purchase orders cover this recommendation"
                )
        business = await self.session.get(Business, business_id)
        if business is None:
            raise NotFoundError("Business not found")
        query = (
            select(SupplierProduct, Supplier)
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .where(
                SupplierProduct.business_id == business_id,
                Supplier.is_active.is_(True),
                SupplierProduct.currency == business.base_currency,
            )
        )
        if stock.product_id:
            query = query.where(SupplierProduct.product_id == stock.product_id)
            target = await self.session.scalar(
                select(Product).where(
                    Product.id == stock.product_id, Product.business_id == business_id
                )
            )
        else:
            query = query.where(SupplierProduct.ingredient_id == stock.ingredient_id)
            target = await self.session.scalar(
                select(Ingredient).where(
                    Ingredient.id == stock.ingredient_id,
                    Ingredient.business_id == business_id,
                )
            )
        if target is None:
            raise NotFoundError("Recommended product or ingredient no longer exists")
        if forecast_reorder:
            selected_product_id = UUID(str(recommendation.provenance["supplier_product_id"]))
            query = query.where(SupplierProduct.id == selected_product_id)
        row = (
            await self.session.execute(query.order_by(SupplierProduct.unit_cost).limit(1))
        ).first()
        if row is None:
            raise ConflictError("No active supplier product is priced in the business currency")
        price, supplier = row
        if price.unit_cost <= 0:
            raise ConflictError("Supplier price is invalid; update supplier pricing first")
        quantity = max(quantity, price.minimum_order_quantity)
        if forecast_reorder and price.unit_cost != Decimal(
            str(recommendation.provenance["unit_cost"])
        ):
            raise ConflictError(
                "Supplier price changed; regenerate the recommendation before review"
            )
        if forecast_reorder and price.lead_time_days != int(
            recommendation.provenance["supplier_lead_time_days"]
        ):
            raise ConflictError(
                "Supplier lead time changed; regenerate the recommendation before review"
            )
        total = (quantity * price.unit_cost).quantize(Decimal("0.01"))
        return {
            "recommendation_id": recommendation.id,
            "item_name": target.name,
            "quantity": quantity,
            "unit": target.unit,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "supplier_product_id": price.id,
            "unit_cost": price.unit_cost,
            "estimated_total": total,
            "currency": business.base_currency,
            "recommended_date": recommendation.provenance.get("recommended_date")
            if forecast_reorder
            else None,
        }

    async def approve_reorder(
        self,
        business_id: UUID,
        recommendation_id: UUID,
        actor_id: UUID,
        request_id: str | None,
        approval: ReorderApproval,
    ) -> Purchase:
        recommendation = await self.session.scalar(
            select(Recommendation)
            .where(
                Recommendation.id == recommendation_id,
                Recommendation.business_id == business_id,
            )
            .with_for_update()
        )
        if recommendation is None:
            raise NotFoundError("Recommendation not found")
        if recommendation.status == "executed" and recommendation.executed_purchase_id:
            existing = await self.session.get(Purchase, recommendation.executed_purchase_id)
            if existing:
                return existing
        if recommendation.status != "pending" or recommendation.recommendation_type != "reorder":
            raise ConflictError("Only pending reorder recommendations can be approved")
        if recommendation.target_type != "inventory":
            raise ConflictError("This recommendation does not identify an inventory item")
        try:
            inventory_id = UUID(recommendation.target_id)
        except ValueError as exc:
            raise ConflictError("Recommendation inventory reference is invalid") from exc
        stock = await self.session.scalar(
            select(Inventory)
            .where(Inventory.id == inventory_id, Inventory.business_id == business_id)
            .with_for_update()
        )
        if stock is None:
            raise NotFoundError("Recommended inventory item no longer exists")
        forecast_reorder = (recommendation.provenance or {}).get(
            "source"
        ) == "forecast_reorder_engine"
        if forecast_reorder:
            quantity = Decimal(str(recommendation.provenance["recommended_quantity"]))
            if Decimal(stock.quantity) != Decimal(
                str(recommendation.provenance["inventory_on_hand"])
            ):
                raise ConflictError(
                    "Inventory changed; regenerate the recommendation before approval"
                )
            if await self._outstanding_quantity(business_id, stock) != Decimal(
                str(recommendation.provenance["outstanding_purchase_quantity"])
            ):
                raise ConflictError(
                    "Open purchase orders changed; regenerate the recommendation before approval"
                )
        else:
            quantity = max(stock.reorder_point + stock.safety_stock - stock.quantity, Decimal(0))
            quantity = max(
                quantity - await self._outstanding_quantity(business_id, stock), Decimal(0)
            )
            if quantity <= 0:
                raise ConflictError(
                    "Current stock and outstanding purchase orders cover this recommendation"
                )
        business = await self.session.get(Business, business_id)
        if business is None:
            raise NotFoundError("Business not found")
        supplier_item_query = (
            select(SupplierProduct, Supplier)
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .where(
                SupplierProduct.business_id == business_id,
                Supplier.is_active.is_(True),
                SupplierProduct.currency == business.base_currency,
            )
        )
        if stock.product_id:
            supplier_item_query = supplier_item_query.where(
                SupplierProduct.product_id == stock.product_id
            )
        else:
            supplier_item_query = supplier_item_query.where(
                SupplierProduct.ingredient_id == stock.ingredient_id
            )
        if forecast_reorder:
            supplier_item_query = supplier_item_query.where(
                SupplierProduct.id == UUID(str(recommendation.provenance["supplier_product_id"]))
            )
        supplier_item = (
            await self.session.execute(
                supplier_item_query.order_by(SupplierProduct.unit_cost.asc())
                .limit(1)
                .with_for_update()
            )
        ).first()
        if supplier_item is None:
            raise ConflictError("No active supplier product is priced in the business currency")
        price, supplier = supplier_item
        if price.unit_cost <= 0:
            raise ConflictError("Supplier price is invalid; update supplier pricing first")
        quantity = max(quantity, price.minimum_order_quantity)
        if forecast_reorder and price.unit_cost != Decimal(
            str(recommendation.provenance["unit_cost"])
        ):
            raise ConflictError(
                "Supplier price changed; regenerate the recommendation before approval"
            )
        if forecast_reorder and price.lead_time_days != int(
            recommendation.provenance["supplier_lead_time_days"]
        ):
            raise ConflictError(
                "Supplier lead time changed; regenerate the recommendation before approval"
            )
        if (
            price.id != approval.supplier_product_id
            or quantity != approval.quantity
            or price.unit_cost != approval.unit_cost
        ):
            raise ConflictError(
                "Stock or supplier pricing changed; review the updated purchase quote"
            )
        purchase_item = PurchaseItemCreate(
            product_id=stock.product_id,
            ingredient_id=stock.ingredient_id,
            quantity=quantity,
            unit_cost=price.unit_cost,
        )
        recommendation.status = "executed"
        recommendation.approved_by = actor_id
        recommendation.approved_at = datetime.now(UTC)
        recommendation.provenance = {
            **(recommendation.provenance or {}),
            "owner_approval": {
                "approved_by": str(actor_id),
                "approved_at": recommendation.approved_at.isoformat(),
                "supplier_id": str(supplier.id),
                "supplier_product_id": str(price.id),
                "quantity": str(quantity),
                "unit_cost": str(price.unit_cost),
            },
        }
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="recommendation.owner_approved",
            entity_type="recommendation",
            entity_id=recommendation.id,
            request_id=request_id,
            metadata={"supplier_id": str(supplier.id), "quantity": str(quantity)},
        )
        purchase = await ProcurementService(self.session).create_order(
            business_id,
            actor_id,
            PurchaseCreate(
                supplier_id=supplier.id,
                items=[purchase_item],
                currency=business.base_currency,
                idempotency_key=f"recommendation:{recommendation.id}",
            ),
            request_id,
            commit_transaction=False,
        )
        recommendation.status = "executed"
        recommendation.approved_by = actor_id
        recommendation.executed_purchase_id = purchase.id
        await self.session.commit()
        return purchase
