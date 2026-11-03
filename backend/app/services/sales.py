from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Business,
    Customer,
    Inventory,
    InventoryMovement,
    Order,
    OrderItem,
    OutboxEvent,
    Payment,
    Product,
    Recipe,
)
from app.repositories.sales import SalesRepository
from app.schemas.sales import OrderCreate
from app.services.accounting import add_journal
from app.services.audit import add_audit_entry
from app.services.inventory import InventoryService, inventory_level
from app.services.units import convert_quantity

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class SalesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = SalesRepository(session)

    async def list_orders(
        self, business_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[Order]:
        return await self.repository.list_orders(business_id, limit, offset)

    async def create_order(
        self, business_id: UUID, actor_id: UUID, payload: OrderCreate, request_id: str | None
    ) -> Order:
        base_currency = await self.session.scalar(
            select(Business.base_currency).where(Business.id == business_id)
        )
        if payload.currency != base_currency:
            raise ConflictError("Sale currency must match the business base currency")
        if payload.idempotency_key:
            existing = await self.repository.order_by_idempotency(
                business_id, payload.idempotency_key
            )
            if existing:
                return existing
        if payload.customer_id:
            customer = await self.session.scalar(
                select(Customer.id).where(
                    Customer.id == payload.customer_id, Customer.business_id == business_id
                )
            )
            if customer is None:
                raise NotFoundError("Customer not found")
        quantities: dict[UUID, Decimal] = {}
        for line in payload.items:
            quantities[line.product_id] = (
                quantities.get(line.product_id, Decimal("0")) + line.quantity
            )
        products = await self.session.scalars(
            select(Product).where(
                Product.business_id == business_id,
                Product.id.in_(quantities),
                Product.is_active.is_(True),
            )
        )
        product_by_id = {product.id: product for product in products}
        if set(product_by_id) != set(quantities):
            raise NotFoundError("One or more products were not found or are inactive")
        recipes = list(
            await self.session.scalars(
                select(Recipe)
                .options(selectinload(Recipe.ingredients))
                .where(
                    Recipe.business_id == business_id,
                    Recipe.product_id.in_(quantities),
                )
            )
        )
        recipe_by_product = {recipe.product_id: recipe for recipe in recipes}
        stock_needs: dict[tuple[str, UUID], Decimal] = {}
        line_needs: list[list[tuple[tuple[str, UUID], Decimal]]] = []
        for line in payload.items:
            product = product_by_id[line.product_id]
            recipe = recipe_by_product.get(product.id)
            needs: list[tuple[tuple[str, UUID], Decimal]] = []
            if recipe:
                sold_units = convert_quantity(line.quantity, product.unit, recipe.yield_unit)
                yield_count = sold_units / recipe.yield_quantity
                for component in recipe.ingredients:
                    key = ("ingredient", component.ingredient_id)
                    needed = (component.quantity * yield_count).quantize(Decimal("0.001"))
                    stock_needs[key] = stock_needs.get(key, Decimal("0")) + needed
                    needs.append((key, needed))
            else:
                key = ("product", product.id)
                stock_needs[key] = stock_needs.get(key, Decimal("0")) + line.quantity
                needs.append((key, line.quantity))
            line_needs.append(needs)
        subtotal = sum(
            (money(product_by_id[item.product_id].price * item.quantity) for item in payload.items),
            Decimal("0"),
        )
        discount = money(payload.discount)
        if discount > subtotal:
            raise ConflictError("Discount cannot exceed the order subtotal")
        total = money(subtotal - discount)
        if total <= 0:
            raise ConflictError("A sale total must be greater than zero")
        product_stock_ids = {item_id for kind, item_id in stock_needs if kind == "product"}
        ingredient_stock_ids = {item_id for kind, item_id in stock_needs if kind == "ingredient"}
        stock_filter = []
        if product_stock_ids:
            stock_filter.append(Inventory.product_id.in_(product_stock_ids))
        if ingredient_stock_ids:
            stock_filter.append(Inventory.ingredient_id.in_(ingredient_stock_ids))
        inventory_rows = list(
            await self.session.scalars(
                select(Inventory)
                .where(
                    Inventory.business_id == business_id,
                    or_(*stock_filter),
                    Inventory.location == "Main",
                )
                .order_by(Inventory.id)
                .with_for_update()
            )
        )
        inventory_by_item = {
            ("product", row.product_id)
            if row.product_id
            else ("ingredient", row.ingredient_id): row
            for row in inventory_rows
        }
        if set(inventory_by_item) != set(stock_needs):
            raise ConflictError("Every consumed stock item needs a Main inventory record")
        for key, needed in stock_needs.items():
            if inventory_by_item[key].quantity < needed:
                raise ConflictError("Insufficient stock for a sold product or recipe ingredient")
        order = Order(
            business_id=business_id,
            customer_id=payload.customer_id,
            status="completed",
            subtotal=subtotal,
            discount=discount,
            tax=Decimal("0"),
            total=total,
            currency=payload.currency,
            idempotency_key=payload.idempotency_key,
            created_by=actor_id,
        )
        cost_of_goods = Decimal("0")
        for line, needs in zip(payload.items, line_needs, strict=True):
            product = product_by_id[line.product_id]
            line_total = money(product.price * line.quantity)
            line_cost = sum(
                (inventory_by_item[key].unit_cost_average * quantity for key, quantity in needs),
                Decimal("0"),
            )
            cost_of_goods += money(line_cost)
            unit_cost = (line_cost / line.quantity).quantize(Decimal("0.0001"))
            order.items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,
                    quantity=line.quantity,
                    unit_price=product.price,
                    unit_cost=unit_cost,
                    line_total=line_total,
                )
            )
        self.session.add(order)
        await self.session.flush()
        for key, quantity in stock_needs.items():
            inventory = inventory_by_item[key]
            previous_level = inventory_level(
                inventory.quantity,
                inventory.reorder_point,
                inventory.minimum_stock,
                inventory.safety_stock,
            )
            await InventoryService(self.session).consume_batches(business_id, inventory, quantity)
            result = await self.session.execute(
                update(Inventory)
                .where(
                    Inventory.id == inventory.id,
                    Inventory.business_id == business_id,
                    Inventory.quantity >= quantity,
                )
                .values(quantity=Inventory.quantity - quantity)
                .returning(Inventory.quantity)
            )
            next_quantity = result.scalar_one_or_none()
            if next_quantity is None:
                raise ConflictError("Insufficient stock for a product or recipe ingredient")
            inventory.quantity = next_quantity
            next_level = inventory_level(
                next_quantity,
                inventory.reorder_point,
                inventory.minimum_stock,
                inventory.safety_stock,
            )
            self.session.add(
                InventoryMovement(
                    business_id=business_id,
                    inventory_id=inventory.id,
                    quantity_delta=-quantity,
                    reason="recipe_sale" if key[0] == "ingredient" else "sale",
                    reference=str(order.id),
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
                        "quantity_delta": str(-quantity),
                        "reason": "recipe_sale" if key[0] == "ingredient" else "sale",
                        "order_id": str(order.id),
                    },
                )
            )
            if next_level != previous_level and next_level in {"low", "critical", "out_of_stock"}:
                event_type = {
                    "low": "STOCK_LOW",
                    "critical": "STOCK_CRITICAL",
                    "out_of_stock": "STOCK_OUT_OF_STOCK",
                }[next_level]
                self.session.add(
                    OutboxEvent(
                        business_id=business_id,
                        event_type=event_type,
                        schema_version=1,
                        aggregate_type="inventory",
                        aggregate_id=str(inventory.id),
                        payload={
                            "inventory_id": str(inventory.id),
                            "quantity": str(next_quantity),
                            "reorder_point": str(inventory.reorder_point),
                            "level": next_level,
                        },
                    )
                )
        payment = Payment(
            business_id=business_id,
            order_id=order.id,
            amount=total,
            currency=payload.currency,
            status="completed",
            method=payload.payment_method,
        )
        self.session.add(payment)
        add_journal(
            self.session,
            business_id=business_id,
            source_type="sale",
            source_id=order.id,
            debit_account="Cash",
            credit_account="Sales Revenue",
            amount=total,
            currency=payload.currency,
        )
        if cost_of_goods > 0:
            add_journal(
                self.session,
                business_id=business_id,
                source_type="sale",
                source_id=order.id,
                debit_account="Cost of Goods Sold",
                credit_account="Inventory Asset",
                amount=cost_of_goods,
                currency=payload.currency,
            )
        self.session.add(
            OutboxEvent(
                business_id=business_id,
                event_type="SALE_CREATED",
                schema_version=1,
                aggregate_type="order",
                aggregate_id=str(order.id),
                payload={
                    "order_id": str(order.id),
                    "total": str(total),
                    "currency": payload.currency,
                    "item_count": len(payload.items),
                },
            )
        )
        self.session.add(
            OutboxEvent(
                business_id=business_id,
                event_type="PAYMENT_COMPLETED",
                schema_version=1,
                aggregate_type="payment",
                aggregate_id=str(payment.id),
                payload={
                    "payment_id": str(payment.id),
                    "order_id": str(order.id),
                    "amount": str(total),
                    "currency": payload.currency,
                },
            )
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="order.created",
            entity_type="order",
            entity_id=order.id,
            request_id=request_id,
            metadata={"total": str(total), "currency": payload.currency},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if payload.idempotency_key:
                existing = await self.repository.order_by_idempotency(
                    business_id, payload.idempotency_key
                )
                if existing:
                    return existing
            raise ConflictError("Order could not be saved due to a conflicting request") from exc
        return (
            await self.repository.order_by_idempotency(business_id, payload.idempotency_key)
            if payload.idempotency_key
            else order
        )
