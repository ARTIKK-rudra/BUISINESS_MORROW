from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Business,
    GoodsReceipt,
    GoodsReceiptItem,
    Ingredient,
    Product,
    Purchase,
    PurchaseItem,
    Supplier,
    SupplierPriceHistory,
    SupplierProduct,
)


class SupplierIntelligenceService:
    """Build supplier measures from recorded catalogs, orders, receipts and price history."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    async def list(self, business_id: UUID) -> list[dict]:
        business = await self.session.get(Business, business_id)
        currency = business.base_currency if business else "USD"
        suppliers = list(
            await self.session.scalars(
                select(Supplier).where(Supplier.business_id == business_id).order_by(Supplier.name)
            )
        )
        if not suppliers:
            return []
        supplier_ids = [supplier.id for supplier in suppliers]

        purchases = list(
            await self.session.scalars(
                select(Purchase)
                .where(
                    Purchase.business_id == business_id,
                    Purchase.supplier_id.in_(supplier_ids),
                    Purchase.status != "draft",
                )
                .order_by(Purchase.created_at.desc())
            )
        )
        purchases_by_supplier: dict[UUID, list[Purchase]] = {}
        for purchase in purchases:
            purchases_by_supplier.setdefault(purchase.supplier_id, []).append(purchase)

        lines = list(
            await self.session.execute(
                select(PurchaseItem, Purchase)
                .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
                .where(
                    Purchase.business_id == business_id,
                    Purchase.supplier_id.in_(supplier_ids),
                    Purchase.status != "draft",
                )
            )
        )
        line_ids = [line.id for line, _purchase in lines]
        receipt_times: dict[UUID, datetime] = {}
        if line_ids:
            receipt_rows = await self.session.execute(
                select(
                    GoodsReceiptItem.purchase_item_id,
                    func.max(GoodsReceipt.received_at),
                )
                .join(
                    GoodsReceipt,
                    GoodsReceipt.id == GoodsReceiptItem.goods_receipt_id,
                )
                .where(GoodsReceiptItem.purchase_item_id.in_(line_ids))
                .group_by(GoodsReceiptItem.purchase_item_id)
            )
            receipt_times = {line_id: stamp for line_id, stamp in receipt_rows}

        offers = list(
            await self.session.scalars(
                select(SupplierProduct)
                .where(
                    SupplierProduct.business_id == business_id,
                    SupplierProduct.supplier_id.in_(supplier_ids),
                )
                .order_by(SupplierProduct.created_at.desc())
            )
        )
        product_ids = {offer.product_id for offer in offers if offer.product_id}
        ingredient_ids = {offer.ingredient_id for offer in offers if offer.ingredient_id}
        products = (
            {
                row.id: row
                for row in await self.session.scalars(
                    select(Product).where(
                        Product.business_id == business_id,
                        Product.id.in_(product_ids),
                    )
                )
            }
            if product_ids
            else {}
        )
        ingredients = (
            {
                row.id: row
                for row in await self.session.scalars(
                    select(Ingredient).where(
                        Ingredient.business_id == business_id,
                        Ingredient.id.in_(ingredient_ids),
                    )
                )
            }
            if ingredient_ids
            else {}
        )

        offer_ids = [offer.id for offer in offers]
        histories_by_offer: dict[UUID, list[SupplierPriceHistory]] = {}
        if offer_ids:
            ranked = (
                select(
                    SupplierPriceHistory.id.label("id"),
                    SupplierPriceHistory.supplier_product_id.label("supplier_product_id"),
                    SupplierPriceHistory.unit_cost.label("unit_cost"),
                    SupplierPriceHistory.currency.label("currency"),
                    SupplierPriceHistory.effective_at.label("effective_at"),
                    func.row_number()
                    .over(
                        partition_by=SupplierPriceHistory.supplier_product_id,
                        order_by=(
                            SupplierPriceHistory.effective_at.desc(),
                            SupplierPriceHistory.id.desc(),
                        ),
                    )
                    .label("position"),
                )
                .where(SupplierPriceHistory.supplier_product_id.in_(offer_ids))
                .subquery()
            )
            history_rows = await self.session.execute(
                select(ranked)
                .where(ranked.c.position <= 12)
                .order_by(ranked.c.supplier_product_id, ranked.c.effective_at.desc())
            )
            for row in history_rows:
                point = SupplierPriceHistory(
                    id=row.id,
                    supplier_product_id=row.supplier_product_id,
                    unit_cost=row.unit_cost,
                    currency=row.currency,
                    effective_at=row.effective_at,
                )
                histories_by_offer.setdefault(row.supplier_product_id, []).append(point)

        lines_by_supplier_item: dict[
            tuple[UUID, str, UUID], list[tuple[PurchaseItem, Purchase]]
        ] = {}
        delivered_by_supplier: dict[UUID, list[tuple[PurchaseItem, Purchase, datetime]]] = {}
        for line, purchase in lines:
            if line.product_id:
                item_type, item_id = "product", line.product_id
            elif line.ingredient_id:
                item_type, item_id = "ingredient", line.ingredient_id
            else:
                continue
            lines_by_supplier_item.setdefault(
                (purchase.supplier_id, item_type, item_id), []
            ).append((line, purchase))
            received_at = receipt_times.get(line.id)
            if received_at is not None and line.received_quantity >= line.quantity:
                delivered_by_supplier.setdefault(purchase.supplier_id, []).append(
                    (line, purchase, received_at)
                )

        delivered_stats: dict[UUID, dict] = {}
        for supplier_id, supplier_lines in delivered_by_supplier.items():
            actual_lead_days: list[Decimal] = []
            on_time_count = 0
            reliability_observation_count = 0
            for _line, purchase, received_at in supplier_lines:
                placed_at = self._aware(purchase.created_at)
                actual_at = self._aware(received_at)
                actual_lead_days.append(
                    max(
                        Decimal(str((actual_at - placed_at).total_seconds())) / Decimal(86400),
                        Decimal(0),
                    )
                )
                if purchase.expected_at is not None:
                    reliability_observation_count += 1
                    if actual_at <= self._aware(purchase.expected_at):
                        on_time_count += 1
            delivered_stats[supplier_id] = {
                "actual_lead_days": actual_lead_days,
                "on_time_count": on_time_count,
                "reliability_observation_count": reliability_observation_count,
            }

        suppliers_by_id = {supplier.id: supplier for supplier in suppliers}
        offers_by_supplier: dict[UUID, list[dict]] = {}
        for offer in offers:
            if offer.product_id:
                item = products.get(offer.product_id)
                item_type, item_id = "product", offer.product_id
            else:
                item = ingredients.get(offer.ingredient_id)
                item_type, item_id = "ingredient", offer.ingredient_id
            if item is None:
                continue
            matching = lines_by_supplier_item.get((offer.supplier_id, item_type, item_id), [])
            delivered = [
                (line, purchase)
                for line, purchase in matching
                if line.id in receipt_times and line.received_quantity >= line.quantity
            ]
            expected_matches = [
                (line, purchase) for line, purchase in delivered if purchase.expected_at is not None
            ]
            offer_on_time = sum(
                1
                for _line, purchase in expected_matches
                if self._aware(receipt_times[_line.id]) <= self._aware(purchase.expected_at)
            )
            history = histories_by_offer.get(offer.id, [])
            chronological = list(reversed(history))
            change = None
            if len(chronological) >= 2 and chronological[0].unit_cost:
                change = (
                    (chronological[-1].unit_cost - chronological[0].unit_cost)
                    / chronological[0].unit_cost
                    * Decimal(100)
                ).quantize(Decimal("0.01"))
            offers_by_supplier.setdefault(offer.supplier_id, []).append(
                {
                    "supplier_product_id": offer.id,
                    "item_id": item_id,
                    "item_name": item.name,
                    "item_type": item_type,
                    "available": bool(
                        item.is_active and suppliers_by_id[offer.supplier_id].is_active
                    ),
                    "unit_cost": offer.unit_cost,
                    "currency": offer.currency,
                    "lead_time_days": offer.lead_time_days,
                    "minimum_order_quantity": offer.minimum_order_quantity,
                    "price_change_percent": change,
                    "price_observations": len(history),
                    "price_history": [
                        {
                            "unit_cost": point.unit_cost,
                            "currency": point.currency,
                            "effective_at": point.effective_at,
                        }
                        for point in history
                    ],
                    "purchase_quantity": sum(
                        (line.quantity for line, _purchase in matching),
                        Decimal(0),
                    ),
                    "purchase_count": len({purchase.id for _line, purchase in matching}),
                    "delivered_line_count": len(delivered),
                    "on_time_line_count": offer_on_time,
                    "reliability_observation_count": len(expected_matches),
                }
            )

        output = []
        for supplier in suppliers:
            supplier_purchases = purchases_by_supplier.get(supplier.id, [])
            history = delivered_stats.get(supplier.id, {})
            expected_count = history.get("reliability_observation_count", 0)
            actual_days = history.get("actual_lead_days", [])
            output.append(
                {
                    "id": supplier.id,
                    "name": supplier.name,
                    "email": supplier.email,
                    "contact_name": supplier.contact_name,
                    "is_active": supplier.is_active,
                    "availability_count": sum(
                        1 for offer in offers_by_supplier.get(supplier.id, []) if offer["available"]
                    ),
                    "purchase_count": len(supplier_purchases),
                    "purchase_spend": sum(
                        (
                            purchase.total
                            for purchase in supplier_purchases
                            if purchase.currency == currency
                        ),
                        Decimal(0),
                    ),
                    "currency": currency,
                    "delivered_line_count": len(delivered_by_supplier.get(supplier.id, [])),
                    "reliability_observation_count": expected_count,
                    "on_time_rate": (
                        (Decimal(history["on_time_count"]) / Decimal(expected_count)).quantize(
                            Decimal("0.0001")
                        )
                        if expected_count
                        else None
                    ),
                    "average_actual_lead_days": (
                        (sum(actual_days) / Decimal(len(actual_days))).quantize(Decimal("0.1"))
                        if actual_days
                        else None
                    ),
                    "offers": offers_by_supplier.get(supplier.id, []),
                }
            )
        return output
