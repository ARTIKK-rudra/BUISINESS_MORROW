from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Business,
    GoodsReceipt,
    GoodsReceiptItem,
    Ingredient,
    Inventory,
    InventoryBatch,
    InventoryMovement,
    OutboxEvent,
    Product,
    Purchase,
    PurchaseItem,
    Supplier,
    SupplierProduct,
)
from app.schemas.procurement import GoodsReceiptCreate, PurchaseCreate
from app.services.accounting import add_journal
from app.services.audit import add_audit_entry


class ProcurementService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_orders(self, business_id: UUID, limit: int, offset: int) -> list[Purchase]:
        return list(
            await self.session.scalars(
                select(Purchase)
                .options(selectinload(Purchase.items))
                .where(Purchase.business_id == business_id)
                .order_by(Purchase.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    async def create_order(
        self,
        business_id: UUID,
        actor_id: UUID,
        payload: PurchaseCreate,
        request_id: str | None,
        *,
        commit_transaction: bool = True,
    ) -> Purchase:
        base_currency = await self.session.scalar(
            select(Business.base_currency).where(Business.id == business_id)
        )
        if payload.currency != base_currency:
            raise ConflictError("Purchase currency must match the business base currency")
        if payload.idempotency_key:
            existing = await self.session.scalar(
                select(Purchase)
                .options(selectinload(Purchase.items))
                .where(
                    Purchase.business_id == business_id,
                    Purchase.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return existing
        supplier = await self.session.scalar(
            select(Supplier).where(
                Supplier.id == payload.supplier_id,
                Supplier.business_id == business_id,
                Supplier.is_active.is_(True),
            )
        )
        if supplier is None:
            raise NotFoundError("Supplier not found")
        product_ids = {line.product_id for line in payload.items if line.product_id}
        ingredient_ids = {line.ingredient_id for line in payload.items if line.ingredient_id}
        products = (
            {
                row.id: row
                for row in await self.session.scalars(
                    select(Product).where(
                        Product.business_id == business_id, Product.id.in_(product_ids)
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
                        Ingredient.business_id == business_id, Ingredient.id.in_(ingredient_ids)
                    )
                )
            }
            if ingredient_ids
            else {}
        )
        if set(products) != product_ids or set(ingredients) != ingredient_ids:
            raise NotFoundError("One or more purchase stock items were not found")
        supplier_offers = list(
            await self.session.scalars(
                select(SupplierProduct).where(
                    SupplierProduct.business_id == business_id,
                    SupplierProduct.supplier_id == supplier.id,
                    or_(
                        SupplierProduct.product_id.in_(product_ids) if product_ids else False,
                        SupplierProduct.ingredient_id.in_(ingredient_ids)
                        if ingredient_ids
                        else False,
                    ),
                )
            )
        )
        lead_by_item = {
            ("product", offer.product_id)
            if offer.product_id
            else ("ingredient", offer.ingredient_id): offer.lead_time_days
            for offer in supplier_offers
        }
        item_leads = [
            lead_by_item.get(
                ("product", line.product_id)
                if line.product_id
                else ("ingredient", line.ingredient_id)
            )
            for line in payload.items
        ]
        known_leads = [lead for lead in item_leads if lead is not None]
        expected_at = datetime.now(UTC) + timedelta(days=max(known_leads)) if known_leads else None
        total = sum(
            (line.quantity * line.unit_cost for line in payload.items), Decimal("0")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        purchase = Purchase(
            business_id=business_id,
            supplier_id=supplier.id,
            status="ordered",
            total=total,
            currency=payload.currency,
            expected_at=expected_at,
            idempotency_key=payload.idempotency_key,
            created_by=actor_id,
            items=[
                PurchaseItem(
                    product_id=line.product_id,
                    ingredient_id=line.ingredient_id,
                    quantity=line.quantity,
                    received_quantity=Decimal("0"),
                    unit_cost=line.unit_cost,
                )
                for line in payload.items
            ],
        )
        self.session.add(purchase)
        await self.session.flush()
        self.session.add(
            OutboxEvent(
                business_id=business_id,
                event_type="PURCHASE_CREATED",
                schema_version=1,
                aggregate_type="purchase",
                aggregate_id=str(purchase.id),
                payload={
                    "purchase_id": str(purchase.id),
                    "supplier_id": str(supplier.id),
                    "total": str(total),
                    "currency": payload.currency,
                },
            )
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="purchase_order.created",
            entity_type="purchase",
            entity_id=purchase.id,
            request_id=request_id,
            metadata={"total": str(total), "currency": payload.currency},
        )
        try:
            if commit_transaction:
                await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if payload.idempotency_key:
                existing = await self.session.scalar(
                    select(Purchase)
                    .options(selectinload(Purchase.items))
                    .where(
                        Purchase.business_id == business_id,
                        Purchase.idempotency_key == payload.idempotency_key,
                    )
                )
                if existing:
                    return existing
            raise ConflictError("Purchase order conflicts with an existing request") from exc
        return await self.session.scalar(
            select(Purchase).options(selectinload(Purchase.items)).where(Purchase.id == purchase.id)
        )

    async def receive(
        self,
        business_id: UUID,
        actor_id: UUID,
        purchase_id: UUID,
        payload: GoodsReceiptCreate,
        request_id: str | None,
    ) -> GoodsReceipt:
        if payload.idempotency_key:
            existing = await self.session.scalar(
                select(GoodsReceipt)
                .options(selectinload(GoodsReceipt.items))
                .where(
                    GoodsReceipt.business_id == business_id,
                    GoodsReceipt.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return existing
        purchase = await self.session.scalar(
            select(Purchase)
            .where(Purchase.id == purchase_id, Purchase.business_id == business_id)
            .with_for_update()
        )
        if purchase is None:
            raise NotFoundError("Purchase order not found")
        if purchase.status not in {"ordered", "partially_received"}:
            raise ConflictError("This purchase order cannot receive more stock")
        item_ids = {line.purchase_item_id for line in payload.items}
        order_items = list(
            await self.session.scalars(
                select(PurchaseItem)
                .where(
                    PurchaseItem.purchase_id == purchase.id,
                    PurchaseItem.id.in_(item_ids),
                )
                .with_for_update()
            )
        )
        by_id = {item.id: item for item in order_items}
        if set(by_id) != item_ids:
            raise NotFoundError("One or more purchase lines were not found")
        receipt = GoodsReceipt(
            business_id=business_id,
            purchase_id=purchase.id,
            received_by=actor_id,
            idempotency_key=payload.idempotency_key,
            items=[],
        )
        self.session.add(receipt)
        await self.session.flush()
        received_value = Decimal("0")
        for line in payload.items:
            order_line = by_id[line.purchase_item_id]
            remaining = order_line.quantity - order_line.received_quantity
            if line.quantity > remaining:
                raise ConflictError("Received quantity exceeds the outstanding purchase quantity")
            if order_line.product_id:
                stock_filter = Inventory.product_id == order_line.product_id
                item_id = order_line.product_id
                item_type = "product"
                product = await self.session.get(Product, item_id)
                item_name = product.name if product else "Product"
                minimum = Decimal("0")
                safety = Decimal("0")
                maximum = None
            else:
                stock_filter = Inventory.ingredient_id == order_line.ingredient_id
                item_id = order_line.ingredient_id
                item_type = "ingredient"
                ingredient = await self.session.get(Ingredient, item_id)
                item_name = ingredient.name if ingredient else "Ingredient"
                minimum = ingredient.minimum_stock if ingredient else Decimal("0")
                safety = ingredient.safety_stock if ingredient else Decimal("0")
                maximum = ingredient.maximum_stock if ingredient else None
            inventory = await self.session.scalar(
                select(Inventory)
                .where(
                    Inventory.business_id == business_id,
                    stock_filter,
                    Inventory.location == "Main",
                )
                .with_for_update()
            )
            if inventory is None:
                inventory = Inventory(
                    business_id=business_id,
                    product_id=item_id if item_type == "product" else None,
                    ingredient_id=item_id if item_type == "ingredient" else None,
                    location="Main",
                    minimum_stock=minimum,
                    reorder_point=minimum,
                    safety_stock=safety,
                    maximum_stock=maximum,
                )
                self.session.add(inventory)
                await self.session.flush()
            old_quantity = inventory.quantity
            new_quantity = old_quantity + line.quantity
            result = await self.session.execute(
                update(Inventory)
                .where(Inventory.id == inventory.id, Inventory.business_id == business_id)
                .values(quantity=Inventory.quantity + line.quantity)
                .returning(Inventory.quantity)
            )
            inventory.quantity = result.scalar_one()
            inventory.unit_cost_average = (
                (old_quantity * inventory.unit_cost_average + line.quantity * order_line.unit_cost)
                / new_quantity
            ).quantize(Decimal("0.0001"))
            lot_code = line.lot_code or f"GR-{receipt.id.hex[:10]}-{order_line.id.hex[:6]}"
            batch = InventoryBatch(
                business_id=business_id,
                inventory_id=inventory.id,
                lot_code=lot_code,
                initial_quantity=line.quantity,
                quantity_remaining=line.quantity,
                unit_cost=order_line.unit_cost,
                expires_on=line.expires_on,
            )
            self.session.add(batch)
            await self.session.flush()
            receipt.items.append(
                GoodsReceiptItem(
                    purchase_item_id=order_line.id,
                    inventory_batch_id=batch.id,
                    quantity=line.quantity,
                )
            )
            self.session.add(
                InventoryMovement(
                    business_id=business_id,
                    inventory_id=inventory.id,
                    quantity_delta=line.quantity,
                    reason="goods_received",
                    reference=str(receipt.id),
                    actor_user_id=actor_id,
                )
            )
            self.session.add(
                OutboxEvent(
                    business_id=business_id,
                    event_type="INVENTORY_UPDATED",
                    schema_version=1,
                    aggregate_type="inventory",
                    aggregate_id=str(inventory.id),
                    payload={
                        "inventory_id": str(inventory.id),
                        "item_id": str(item_id),
                        "item_type": item_type,
                        "item_name": item_name,
                        "quantity": str(inventory.quantity),
                        "quantity_delta": str(line.quantity),
                        "reason": "goods_received",
                    },
                )
            )
            order_line.received_quantity += line.quantity
            received_value += line.quantity * order_line.unit_cost
        all_lines = list(
            await self.session.scalars(
                select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
            )
        )
        purchase.status = (
            "received"
            if all(item.received_quantity >= item.quantity for item in all_lines)
            else "partially_received"
        )
        received_value = received_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        currency = purchase.currency
        add_journal(
            self.session,
            business_id=business_id,
            source_type="goods_receipt",
            source_id=receipt.id,
            debit_account="Inventory Asset",
            credit_account="Accounts Payable",
            amount=received_value,
            currency=currency,
        )
        self.session.add(
            OutboxEvent(
                business_id=business_id,
                event_type="GOODS_RECEIVED",
                schema_version=1,
                aggregate_type="goods_receipt",
                aggregate_id=str(receipt.id),
                payload={
                    "receipt_id": str(receipt.id),
                    "purchase_id": str(purchase.id),
                    "value": str(received_value),
                    "currency": currency,
                },
            )
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="goods_received.created",
            entity_type="goods_receipt",
            entity_id=receipt.id,
            request_id=request_id,
            metadata={"purchase_id": str(purchase.id), "value": str(received_value)},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if payload.idempotency_key:
                existing = await self.session.scalar(
                    select(GoodsReceipt)
                    .options(selectinload(GoodsReceipt.items))
                    .where(
                        GoodsReceipt.business_id == business_id,
                        GoodsReceipt.idempotency_key == payload.idempotency_key,
                    )
                )
                if existing:
                    return existing
            raise ConflictError("Goods receipt could not be saved") from exc
        return await self.session.scalar(
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.items))
            .where(GoodsReceipt.id == receipt.id)
        )

    async def list_receipts(self, business_id: UUID, purchase_id: UUID) -> list[GoodsReceipt]:
        return list(
            await self.session.scalars(
                select(GoodsReceipt)
                .options(selectinload(GoodsReceipt.items))
                .where(
                    GoodsReceipt.business_id == business_id,
                    GoodsReceipt.purchase_id == purchase_id,
                )
                .order_by(GoodsReceipt.received_at.desc())
            )
        )
