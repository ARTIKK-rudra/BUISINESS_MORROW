from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Business,
    Ingredient,
    Inventory,
    InventoryBatch,
    InventoryMovement,
    OutboxEvent,
    Product,
)
from app.repositories.inventory import InventoryRepository
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryCreate,
    InventoryThresholdUpdate,
    InventoryWastage,
)
from app.services.accounting import add_journal
from app.services.audit import add_audit_entry


def calculate_adjusted_quantity(current: Decimal, delta: Decimal) -> Decimal:
    result = current + delta
    if result < 0:
        raise ConflictError("Inventory quantity cannot become negative")
    return result


def inventory_level(
    quantity: Decimal,
    reorder_point: Decimal,
    minimum_stock: Decimal = Decimal("0"),
    safety_stock: Decimal = Decimal("0"),
) -> str:
    if quantity <= 0:
        return "out_of_stock"
    minimum = max(reorder_point, minimum_stock)
    if quantity <= safety_stock or (minimum > 0 and quantity <= minimum / Decimal("2")):
        return "critical"
    if quantity <= minimum:
        return "low"
    return "healthy"


class InventoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = InventoryRepository(session)

    async def list_inventory(self, business_id: UUID) -> list[Inventory]:
        return await self.repository.list_inventory_records(business_id)

    async def create(
        self, business_id: UUID, actor_id: UUID, payload: InventoryCreate, request_id: str | None
    ) -> Inventory:
        product = (
            await self.session.scalar(
                select(Product).where(
                    Product.id == payload.product_id, Product.business_id == business_id
                )
            )
            if payload.product_id
            else None
        )
        ingredient = (
            await self.session.scalar(
                select(Ingredient).where(
                    Ingredient.id == payload.ingredient_id,
                    Ingredient.business_id == business_id,
                )
            )
            if payload.ingredient_id
            else None
        )
        if product is None and ingredient is None:
            raise NotFoundError("Product or ingredient not found")
        minimum_stock = (
            payload.minimum_stock
            if "minimum_stock" in payload.model_fields_set
            else ingredient.minimum_stock
            if ingredient
            else payload.reorder_point
        )
        maximum_stock = (
            payload.maximum_stock
            if "maximum_stock" in payload.model_fields_set
            else ingredient.maximum_stock
            if ingredient
            else None
        )
        safety_stock = (
            payload.safety_stock
            if "safety_stock" in payload.model_fields_set
            else ingredient.safety_stock
            if ingredient
            else Decimal("0")
        )
        record = Inventory(
            business_id=business_id,
            product_id=product.id if product else None,
            ingredient_id=ingredient.id if ingredient else None,
            location=payload.location.strip(),
            reorder_point=payload.reorder_point,
            unit_cost_average=payload.unit_cost_average,
            expires_on=payload.expires_on,
            minimum_stock=minimum_stock,
            maximum_stock=maximum_stock,
            safety_stock=safety_stock,
        )
        self.repository.add(record)
        try:
            await self.session.flush()
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="inventory.created",
                entity_type="inventory",
                entity_id=record.id,
                request_id=request_id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Inventory already exists for this product and location") from exc
        await self.session.refresh(record)
        return record

    async def adjust(
        self,
        business_id: UUID,
        actor_id: UUID,
        inventory_id: UUID,
        payload: InventoryAdjust,
        request_id: str | None,
    ) -> Inventory:
        record = await self.repository.get_for_update(business_id, inventory_id)
        if record is None:
            raise NotFoundError("Inventory record not found")
        if payload.quantity_delta < 0:
            await self.consume_batches(
                business_id, record, -payload.quantity_delta, allow_expired=True
            )
        previous_level = inventory_level(
            record.quantity, record.reorder_point, record.minimum_stock, record.safety_stock
        )
        result = await self.session.execute(
            update(Inventory)
            .where(
                Inventory.id == record.id,
                Inventory.business_id == business_id,
                Inventory.quantity + payload.quantity_delta >= 0,
            )
            .values(quantity=Inventory.quantity + payload.quantity_delta)
            .returning(Inventory.quantity)
        )
        next_quantity = result.scalar_one_or_none()
        if next_quantity is None:
            raise ConflictError("Inventory quantity cannot become negative")
        record.quantity = next_quantity
        previous_quantity = next_quantity - payload.quantity_delta
        adjustment_cost = Decimal("0")
        if payload.quantity_delta > 0 and (payload.unit_cost or record.unit_cost_average) > 0:
            cost_per_unit = payload.unit_cost or record.unit_cost_average
            adjustment_cost = (payload.quantity_delta * cost_per_unit).quantize(Decimal("0.01"))
        if payload.quantity_delta > 0 and payload.unit_cost is not None:
            record.unit_cost_average = (
                (
                    previous_quantity * record.unit_cost_average
                    + payload.quantity_delta * payload.unit_cost
                )
                / next_quantity
            ).quantize(Decimal("0.0001"))
        elif payload.quantity_delta < 0:
            adjustment_cost = (-payload.quantity_delta * record.unit_cost_average).quantize(
                Decimal("0.01")
            )
        movement = InventoryMovement(
            business_id=business_id,
            inventory_id=record.id,
            quantity_delta=payload.quantity_delta,
            reason=payload.reason.strip(),
            reference=payload.reference,
            actor_user_id=actor_id,
        )
        self.repository.add(movement)
        if adjustment_cost > 0:
            if payload.quantity_delta > 0:
                debit_account, credit_account = "Inventory Asset", "Inventory Adjustments"
            else:
                debit_account = (
                    "Inventory Wastage"
                    if payload.reason.lower().startswith("wast")
                    else "Inventory Shrinkage"
                )
                credit_account = "Inventory Asset"
            currency = await self.session.scalar(
                select(Business.base_currency).where(Business.id == business_id)
            )
            add_journal(
                self.session,
                business_id=business_id,
                source_type="inventory_adjustment",
                source_id=movement.id,
                debit_account=debit_account,
                credit_account=credit_account,
                amount=adjustment_cost,
                currency=currency or "USD",
            )
        self.repository.add(
            OutboxEvent(
                business_id=business_id,
                event_type="INVENTORY_UPDATED",
                schema_version=1,
                aggregate_type="inventory",
                aggregate_id=str(record.id),
                payload={
                    "inventory_id": str(record.id),
                    "quantity": str(next_quantity),
                    "quantity_delta": str(payload.quantity_delta),
                    "reason": payload.reason.strip(),
                },
            )
        )
        next_level = inventory_level(
            next_quantity, record.reorder_point, record.minimum_stock, record.safety_stock
        )
        if next_level != previous_level and next_level in {"low", "critical", "out_of_stock"}:
            event_type = {
                "critical": "STOCK_CRITICAL",
                "low": "STOCK_LOW",
                "out_of_stock": "STOCK_OUT_OF_STOCK",
            }[next_level]
            self.repository.add(
                OutboxEvent(
                    business_id=business_id,
                    event_type=event_type,
                    schema_version=1,
                    aggregate_type="inventory",
                    aggregate_id=str(record.id),
                    payload={
                        "inventory_id": str(record.id),
                        "quantity": str(next_quantity),
                        "reorder_point": str(record.reorder_point),
                        "level": next_level,
                    },
                )
            )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="inventory.adjusted",
            entity_type="inventory",
            entity_id=record.id,
            request_id=request_id,
            metadata={
                "quantity_delta": str(payload.quantity_delta),
                "reason": payload.reason.strip(),
            },
        )
        await self.repository.commit()
        await self.session.refresh(record)
        return record

    async def wastage(
        self,
        business_id: UUID,
        actor_id: UUID,
        inventory_id: UUID,
        payload: InventoryWastage,
        request_id: str | None,
    ) -> Inventory:
        return await self.adjust(
            business_id,
            actor_id,
            inventory_id,
            InventoryAdjust(
                quantity_delta=-payload.quantity,
                reason=f"wastage: {payload.reason}",
                reference=payload.reference,
            ),
            request_id,
        )

    async def update_thresholds(
        self,
        business_id: UUID,
        actor_id: UUID,
        inventory_id: UUID,
        payload: InventoryThresholdUpdate,
        request_id: str | None,
    ) -> Inventory:
        record = await self.repository.get_for_update(business_id, inventory_id)
        if record is None:
            raise NotFoundError("Inventory record not found")
        if payload.maximum_stock is not None and payload.maximum_stock < payload.minimum_stock:
            raise ConflictError("maximum_stock must be at least minimum_stock")
        record.minimum_stock = payload.minimum_stock
        record.maximum_stock = payload.maximum_stock
        record.safety_stock = payload.safety_stock
        record.reorder_point = payload.minimum_stock
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="inventory.thresholds_updated",
            entity_type="inventory",
            entity_id=record.id,
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def movements(self, business_id: UUID, inventory_id: UUID) -> list[InventoryMovement]:
        if await self.repository.get_for_update(business_id, inventory_id) is None:
            raise NotFoundError("Inventory record not found")
        return await self.repository.movement_history(business_id, inventory_id)

    async def batches(self, business_id: UUID, inventory_id: UUID) -> list[InventoryBatch]:
        if await self.repository.get_for_update(business_id, inventory_id) is None:
            raise NotFoundError("Inventory record not found")
        return list(
            await self.session.scalars(
                select(InventoryBatch)
                .where(
                    InventoryBatch.business_id == business_id,
                    InventoryBatch.inventory_id == inventory_id,
                )
                .order_by(InventoryBatch.expires_on, InventoryBatch.created_at)
            )
        )

    async def consume_batches(
        self,
        business_id: UUID,
        inventory: Inventory,
        quantity: Decimal,
        *,
        allow_expired: bool = False,
    ) -> None:
        batches = list(
            await self.session.scalars(
                select(InventoryBatch)
                .where(
                    InventoryBatch.business_id == business_id,
                    InventoryBatch.inventory_id == inventory.id,
                    InventoryBatch.quantity_remaining > 0,
                )
                .order_by(InventoryBatch.expires_on.asc().nulls_last(), InventoryBatch.created_at)
                .with_for_update()
            )
        )
        today = date.today()
        batched_total = sum((batch.quantity_remaining for batch in batches), Decimal("0"))
        unbatched_quantity = max(inventory.quantity - batched_total, Decimal("0"))
        active_batches = (
            batches
            if allow_expired
            else [
                batch for batch in batches if batch.expires_on is None or batch.expires_on >= today
            ]
        )
        sellable = unbatched_quantity + sum(
            (batch.quantity_remaining for batch in active_batches), Decimal("0")
        )
        if sellable < quantity:
            raise ConflictError("Insufficient unexpired stock")
        remaining = quantity
        for batch in active_batches:
            if remaining <= 0:
                break
            consumed = min(batch.quantity_remaining, remaining)
            batch.quantity_remaining -= consumed
            remaining -= consumed
        if remaining > unbatched_quantity:
            raise ConflictError("Insufficient unexpired stock")

    async def alerts(self, business_id: UUID, expiring_within_days: int = 30) -> list[dict]:
        rows = await self.session.execute(
            select(Inventory, Product.name, Ingredient.name)
            .outerjoin(Product, Inventory.product_id == Product.id)
            .outerjoin(Ingredient, Inventory.ingredient_id == Ingredient.id)
            .where(Inventory.business_id == business_id)
        )
        today = date.today()
        expiry_cutoff = today + timedelta(days=expiring_within_days)
        alerts: list[dict] = []
        for record, product_name, ingredient_name in rows:
            item_type = "product" if record.product_id else "ingredient"
            item_id = record.product_id or record.ingredient_id
            item_name = product_name or ingredient_name or "Stock item"
            minimum = max(record.minimum_stock, record.reorder_point)
            if record.quantity <= 0:
                state = "OUT-OF-STOCK"
            elif record.quantity <= record.safety_stock or (
                minimum > 0 and record.quantity <= minimum / 2
            ):
                state = "CRITICAL"
            elif record.quantity <= minimum:
                state = "LOW"
            else:
                state = "HEALTHY"
            if state != "HEALTHY":
                alerts.append(
                    {
                        "inventory_id": record.id,
                        "item_id": item_id,
                        "item_type": item_type,
                        "item_name": item_name,
                        "location": record.location,
                        "quantity": record.quantity,
                        "state": state,
                        "alert_kind": "RULE_BASED_ALERT",
                        "message": f"{item_name} stock is {state.lower()}",
                    }
                )
            if record.maximum_stock is not None and record.quantity > record.maximum_stock:
                alerts.append(
                    {
                        "inventory_id": record.id,
                        "item_id": item_id,
                        "item_type": item_type,
                        "item_name": item_name,
                        "location": record.location,
                        "quantity": record.quantity,
                        "state": "OVERSTOCK",
                        "alert_kind": "RULE_BASED_ALERT",
                        "message": f"{item_name} is above its maximum stock level",
                    }
                )
            batches = await self.session.scalars(
                select(InventoryBatch).where(
                    InventoryBatch.business_id == business_id,
                    InventoryBatch.inventory_id == record.id,
                    InventoryBatch.quantity_remaining > 0,
                    InventoryBatch.expires_on.is_not(None),
                    InventoryBatch.expires_on <= expiry_cutoff,
                )
            )
            for batch in batches:
                alerts.append(
                    {
                        "inventory_id": record.id,
                        "item_id": item_id,
                        "item_type": item_type,
                        "item_name": item_name,
                        "location": record.location,
                        "quantity": batch.quantity_remaining,
                        "state": "EXPIRING",
                        "alert_kind": "RULE_BASED_ALERT",
                        "expires_on": batch.expires_on,
                        "message": (
                            f"Lot {batch.lot_code} of {item_name} expires on {batch.expires_on}"
                        ),
                    }
                )
            if record.expires_on and today <= record.expires_on <= expiry_cutoff:
                alerts.append(
                    {
                        "inventory_id": record.id,
                        "item_id": item_id,
                        "item_type": item_type,
                        "item_name": item_name,
                        "location": record.location,
                        "quantity": record.quantity,
                        "state": "EXPIRING",
                        "alert_kind": "RULE_BASED_ALERT",
                        "expires_on": record.expires_on,
                        "message": f"{item_name} expires on {record.expires_on}",
                    }
                )
        return alerts
