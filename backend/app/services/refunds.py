from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Inventory,
    InventoryMovement,
    OrderItem,
    OutboxEvent,
    Payment,
    Refund,
)
from app.schemas.sales import RefundCreate
from app.services.accounting import add_journal
from app.services.audit import add_audit_entry


class RefundService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, business_id: UUID, limit: int, offset: int) -> list[Refund]:
        result = await self.session.scalars(
            select(Refund)
            .where(Refund.business_id == business_id)
            .order_by(Refund.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def create(
        self,
        business_id: UUID,
        actor_id: UUID,
        payload: RefundCreate,
        request_id: str | None,
    ) -> Refund:
        if payload.idempotency_key:
            existing = await self.session.scalar(
                select(Refund).where(
                    Refund.business_id == business_id,
                    Refund.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return existing
        payment = await self.session.scalar(
            select(Payment)
            .where(Payment.id == payload.payment_id, Payment.business_id == business_id)
            .with_for_update()
        )
        if payment is None:
            raise NotFoundError("Payment not found")
        if payment.status not in {"completed", "partially_refunded"}:
            raise ConflictError("Only completed payments may be refunded")
        already_refunded = await self.session.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.business_id == business_id,
                Refund.payment_id == payment.id,
                Refund.status == "completed",
            )
        )
        remaining = payment.amount - Decimal(already_refunded or 0)
        if payload.amount > remaining:
            raise ConflictError("Refund exceeds the remaining captured payment")
        if payload.restock and (
            Decimal(already_refunded or 0) > 0 or payload.amount != payment.amount
        ):
            raise ConflictError("Restocking is supported only with the original full refund")
        refund = Refund(
            business_id=business_id,
            payment_id=payment.id,
            amount=payload.amount,
            currency=payment.currency,
            reason=payload.reason,
            status="completed",
            idempotency_key=payload.idempotency_key,
        )
        self.session.add(refund)
        await self.session.flush()
        if payload.restock:
            order_items = list(
                await self.session.scalars(
                    select(OrderItem).where(OrderItem.order_id == payment.order_id)
                )
            )
            product_ids = {item.product_id for item in order_items}
            inventories = list(
                await self.session.scalars(
                    select(Inventory)
                    .where(
                        Inventory.business_id == business_id,
                        Inventory.product_id.in_(product_ids),
                        Inventory.location == "Main",
                    )
                    .order_by(Inventory.id)
                    .with_for_update()
                )
            )
            by_product = {inventory.product_id: inventory for inventory in inventories}
            if set(by_product) != product_ids:
                raise ConflictError("Returned products need Main inventory records")
            restocked_cost = Decimal("0")
            for item in order_items:
                inventory = by_product[item.product_id]
                old_quantity = inventory.quantity
                new_quantity = old_quantity + item.quantity
                result = await self.session.execute(
                    update(Inventory)
                    .where(Inventory.id == inventory.id, Inventory.business_id == business_id)
                    .values(quantity=Inventory.quantity + item.quantity)
                    .returning(Inventory.quantity)
                )
                inventory.quantity = result.scalar_one()
                inventory.unit_cost_average = (
                    (old_quantity * inventory.unit_cost_average + item.quantity * item.unit_cost)
                    / new_quantity
                ).quantize(Decimal("0.0001"))
                restocked_cost += (item.unit_cost * item.quantity).quantize(Decimal("0.01"))
                self.session.add(
                    InventoryMovement(
                        business_id=business_id,
                        inventory_id=inventory.id,
                        quantity_delta=item.quantity,
                        reason="refund_restock",
                        reference=str(refund.id),
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
                            "quantity": str(inventory.quantity),
                            "quantity_delta": str(item.quantity),
                            "reason": "refund_restock",
                        },
                    )
                )
            if restocked_cost > 0:
                add_journal(
                    self.session,
                    business_id=business_id,
                    source_type="refund",
                    source_id=refund.id,
                    debit_account="Inventory Asset",
                    credit_account="Cost of Goods Sold",
                    amount=restocked_cost,
                    currency=payment.currency,
                )
        payment.status = "refunded" if payload.amount == remaining else "partially_refunded"
        add_journal(
            self.session,
            business_id=business_id,
            source_type="refund",
            source_id=refund.id,
            debit_account="Sales Returns",
            credit_account="Cash",
            amount=payload.amount,
            currency=payment.currency,
        )
        self.session.add(
            OutboxEvent(
                business_id=business_id,
                event_type="REFUND_CREATED",
                schema_version=1,
                aggregate_type="refund",
                aggregate_id=str(refund.id),
                payload={
                    "refund_id": str(refund.id),
                    "payment_id": str(payment.id),
                    "amount": str(payload.amount),
                    "currency": payment.currency,
                },
            )
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="refund.created",
            entity_type="refund",
            entity_id=refund.id,
            request_id=request_id,
            metadata={"amount": str(payload.amount), "restock": payload.restock},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if payload.idempotency_key:
                existing = await self.session.scalar(
                    select(Refund).where(
                        Refund.business_id == business_id,
                        Refund.idempotency_key == payload.idempotency_key,
                    )
                )
                if existing:
                    return existing
            raise ConflictError("Refund conflicts with an existing request") from exc
        await self.session.refresh(refund)
        return refund
