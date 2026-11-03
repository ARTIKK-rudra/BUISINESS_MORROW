"""State machine for permission-controlled restaurant provision conversations."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Ingredient,
    Inventory,
    Order,
    Product,
    Purchase,
    PurchaseItem,
    Recipe,
    VoiceContact,
    VoiceConversation,
    VoiceConversationTurn,
)
from app.services.gemini_voice import GeminiVoiceService
from app.services.units import convert_quantity


class ProvisionVoiceService:
    """Only advances a workflow after an explicit, stored authorization."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_owner_shortage_conversation(self, business_id) -> VoiceConversation:
        owner = await self.session.scalar(
            select(VoiceContact).where(
                VoiceContact.business_id == business_id,
                VoiceContact.role == "owner",
                VoiceContact.is_active.is_(True),
                VoiceContact.calling_consent.is_(True),
            )
        )
        if owner is None:
            raise ConflictError("No active owner voice contact with calling consent is configured")
        snapshot = await self.shortage_snapshot(business_id)
        if not snapshot["items"]:
            raise ConflictError("No current rule-based stock shortage is available to call about")
        conversation = VoiceConversation(
            business_id=business_id,
            contact_id=owner.id,
            workflow="owner_shortage_authorization",
            status="awaiting_owner_authorization",
            shortage_snapshot=snapshot,
        )
        self.session.add(conversation)
        await self.session.flush()
        prompt = self.owner_opening_prompt(snapshot)
        self._add_turn(conversation, "agent", prompt, {"stage": "opening"})
        return conversation

    async def shortage_snapshot(self, business_id) -> dict:
        inventory = list(
            await self.session.scalars(
                select(Inventory).where(Inventory.business_id == business_id)
            )
        )
        product_ids = [row.product_id for row in inventory if row.product_id]
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
        ingredient_ids = [row.ingredient_id for row in inventory if row.ingredient_id]
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
        (
            pending_demand,
            demand_orders,
            affected_orders,
            data_quality_issues,
        ) = await self._pending_order_demand(business_id, products)
        committed_inbound = await self._committed_inbound(business_id)

        # A stock item may have several locations.  For replenishment we assess its
        # usable total once, while retaining a stable representative inventory ID for
        # manager/supplier responses and purchase creation.
        stock_groups: dict[tuple[str, object], list[Inventory]] = {}
        for row in inventory:
            key = (
                ("product", row.product_id) if row.product_id else ("ingredient", row.ingredient_id)
            )
            stock_groups.setdefault(key, []).append(row)

        items: list[dict] = []
        for key, rows in stock_groups.items():
            item_type, item_id = key
            item = products.get(item_id) if item_type == "product" else ingredients.get(item_id)
            if item is None:
                data_quality_issues.append(
                    {
                        "type": "inventory_item_not_found",
                        "item_type": item_type,
                        "item_id": str(item_id),
                        "message": "An inventory record references an unavailable catalog item.",
                    }
                )
                continue
            # Prefer Main inventory when it exists, matching normal sales consumption.
            representative = next((row for row in rows if row.location == "Main"), rows[0])
            available = sum((Decimal(row.quantity) for row in rows), Decimal("0"))
            target = sum(
                (
                    max(Decimal(row.reorder_point), Decimal(row.minimum_stock), Decimal(0))
                    for row in rows
                ),
                Decimal("0"),
            )
            demand = pending_demand.get(key, Decimal("0"))
            inbound = committed_inbound.get(key, Decimal("0"))
            physical_shortage = max(target - available, Decimal("0"))
            replenishment_required = max(target + demand - available - inbound, Decimal("0"))
            if demand and available + inbound < demand:
                affected_orders.update(demand_orders.get(key, set()))
            level = self._aggregate_inventory_level(rows, available, target)
            if not physical_shortage and not replenishment_required:
                continue
            items.append(
                {
                    "inventory_id": str(representative.id),
                    "item_id": str(item.id),
                    "item_type": item_type,
                    "name": item.name,
                    "unit": item.unit,
                    "available": str(available),
                    "minimum_target": str(target),
                    "shortage_to_minimum": str(physical_shortage),
                    "pending_demand": str(demand),
                    "committed_inbound": str(inbound),
                    "replenishment_required": str(replenishment_required),
                    "level": level,
                    "locations": [row.location for row in rows],
                }
            )
        pending_orders = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.business_id == business_id,
                Order.status.in_(("pending", "preparing", "ready")),
            )
        )
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "items": items,
            "pending_order_count": int(pending_orders or 0),
            "affected_order_count": len(affected_orders),
            "affected_order_ids": sorted(str(order_id) for order_id in affected_orders),
            "affected_order_calculation": "recipe_and_inventory_assessed",
            "data_quality_issues": data_quality_issues,
        }

    @staticmethod
    def _aggregate_inventory_level(
        rows: list[Inventory], available: Decimal, target: Decimal
    ) -> str:
        if available <= 0:
            return "out_of_stock"
        safety_stock = sum((Decimal(row.safety_stock) for row in rows), Decimal("0"))
        if available <= safety_stock or (target > 0 and available <= target / Decimal("2")):
            return "critical"
        if available <= target:
            return "low"
        return "healthy"

    async def _committed_inbound(self, business_id) -> dict[tuple[str, object], Decimal]:
        rows = await self.session.execute(
            select(
                PurchaseItem.product_id,
                PurchaseItem.ingredient_id,
                func.sum(PurchaseItem.quantity - PurchaseItem.received_quantity),
            )
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .where(
                Purchase.business_id == business_id,
                Purchase.status.in_(("ordered", "partially_received")),
            )
            .group_by(PurchaseItem.product_id, PurchaseItem.ingredient_id)
        )
        return {
            (("product", product_id) if product_id else ("ingredient", ingredient_id)): Decimal(
                quantity
            )
            for product_id, ingredient_id, quantity in rows
            if quantity is not None
        }

    async def _pending_order_demand(
        self, business_id, products: dict
    ) -> tuple[dict[tuple[str, object], Decimal], dict[tuple[str, object], set], set, list[dict]]:
        """Translate open order lines to stock needs without consuming inventory.

        A recipe maps a menu product to ingredients. Products without recipes are
        treated as directly stocked items, exactly as the sales service does. Missing
        recipes/stock records are surfaced as data-quality issues instead of guessed.
        """
        orders = list(
            await self.session.scalars(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.business_id == business_id,
                    Order.status.in_(("pending", "preparing", "ready")),
                )
            )
        )
        product_ids = {line.product_id for order in orders for line in order.items}
        if product_ids:
            missing_products = product_ids - set(products)
            if missing_products:
                product_rows = await self.session.scalars(
                    select(Product).where(
                        Product.business_id == business_id, Product.id.in_(missing_products)
                    )
                )
                products = {**products, **{row.id: row for row in product_rows}}
        recipes = (
            list(
                await self.session.scalars(
                    select(Recipe)
                    .options(selectinload(Recipe.ingredients))
                    .where(Recipe.business_id == business_id, Recipe.product_id.in_(product_ids))
                )
            )
            if product_ids
            else []
        )
        recipe_by_product = {recipe.product_id: recipe for recipe in recipes}
        demand: dict[tuple[str, object], Decimal] = {}
        item_orders: dict[tuple[str, object], set] = {}
        issues: list[dict] = []
        for order in orders:
            for line in order.items:
                product = products.get(line.product_id)
                if product is None:
                    issues.append(
                        {
                            "type": "order_product_missing",
                            "order_id": str(order.id),
                            "product_id": str(line.product_id),
                            "message": (
                                "A pending order refers to a product not found in this tenant."
                            ),
                        }
                    )
                    continue
                recipe = recipe_by_product.get(product.id)
                if recipe is None:
                    key = ("product", product.id)
                    needed = Decimal(line.quantity)
                    demand[key] = demand.get(key, Decimal("0")) + needed
                    item_orders.setdefault(key, set()).add(order.id)
                    continue
                try:
                    yield_count = convert_quantity(
                        Decimal(line.quantity), product.unit, recipe.yield_unit
                    ) / Decimal(recipe.yield_quantity)
                except Exception as exc:
                    issues.append(
                        {
                            "type": "recipe_unit_mismatch",
                            "order_id": str(order.id),
                            "product_id": str(product.id),
                            "message": str(exc),
                        }
                    )
                    continue
                for component in recipe.ingredients:
                    key = ("ingredient", component.ingredient_id)
                    needed = (Decimal(component.quantity) * yield_count).quantize(Decimal("0.001"))
                    demand[key] = demand.get(key, Decimal("0")) + needed
                    item_orders.setdefault(key, set()).add(order.id)

        stock_keys = {
            ("product", row.product_id) if row.product_id else ("ingredient", row.ingredient_id)
            for row in await self.session.scalars(
                select(Inventory).where(Inventory.business_id == business_id)
            )
        }
        affected_orders: set = set()
        for key, order_ids in item_orders.items():
            if key not in stock_keys:
                issues.append(
                    {
                        "type": "missing_inventory_record",
                        "item_type": key[0],
                        "item_id": str(key[1]),
                        "affected_order_ids": sorted(str(order_id) for order_id in order_ids),
                        "message": (
                            "Pending demand cannot be assessed because no inventory record exists."
                        ),
                    }
                )
                affected_orders.update(order_ids)
        # Only demand with a tracked stock item can later contribute to a computed shortage.
        return demand, item_orders, affected_orders, issues

    @staticmethod
    def owner_opening_prompt(snapshot: dict) -> str:
        items = snapshot["items"]
        item_text = "; ".join(
            f"{row['name']}: {row['available']} {row['unit']} available, "
            f"{row['shortage_to_minimum']} {row['unit']} to the configured minimum"
            for row in items
        )
        pending = snapshot["pending_order_count"]
        return (
            "Hello, this is Morrow, your AI Provision Management Assistant. "
            f"I found current stock shortages: {item_text}. "
            f"There are {pending} pending restaurant orders awaiting assessment. "
            "May I contact suppliers to request availability and quotations only? "
            "I will not place a purchase order without your separate approval "
            "of the final terms. You can say yes, no, or call me later; "
            "or press 1 for supplier contact, 2 to decline, or 3 to call later."
        )

    async def record_owner_response(
        self, conversation_id, business_id, transcript: str, digits: str | None = None
    ) -> tuple[VoiceConversation, str]:
        conversation = await self.session.scalar(
            select(VoiceConversation).where(
                VoiceConversation.id == conversation_id,
                VoiceConversation.business_id == business_id,
                VoiceConversation.workflow == "owner_shortage_authorization",
            )
        )
        if conversation is None:
            raise NotFoundError("Owner provision conversation not found")
        if conversation.status not in {
            "awaiting_owner_authorization",
            "dialing",
            "needs_clarification",
        }:
            raise ConflictError("This owner authorization conversation is already resolved")
        decision = await self._owner_decision(transcript, digits)
        self._add_turn(conversation, "caller", transcript or f"DTMF {digits or ''}", decision)
        conversation.turn_count += 1
        now = datetime.now(UTC)
        if decision["outcome"] == "supplier_contact_authorized":
            conversation.supplier_contact_authorized = True
            conversation.purchase_authorized = False
            conversation.status = "supplier_contact_authorized"
            conversation.completed_at = now
            response = (
                "Thank you. I recorded permission to request supplier availability "
                "and quotations only. I will not place an order until you explicitly "
                "approve the final quantities, price, and delivery terms."
            )
        elif decision["outcome"] == "declined":
            conversation.status = "owner_declined"
            conversation.completed_at = now
            response = (
                "Understood. I recorded that supplier contact is not authorized. "
                "No supplier will be called."
            )
        elif decision["outcome"] == "call_later":
            conversation.status = "owner_callback_requested"
            response = (
                "Understood. I recorded a callback request. "
                "No supplier will be called in the meantime."
            )
        else:
            conversation.status = "needs_clarification"
            response = (
                "I need an explicit decision. May I contact suppliers for quotations only? "
                "Please say yes, no, or call me later."
            )
        self._add_turn(conversation, "agent", response, {"stage": "owner_response"})
        return conversation, response

    @staticmethod
    def _deterministic_owner_decision(transcript: str, digits: str | None) -> dict:
        normalized = " ".join(transcript.lower().split())
        if digits == "1":
            return {"outcome": "supplier_contact_authorized", "basis": "dtmf"}
        if digits == "2":
            return {"outcome": "declined", "basis": "dtmf"}
        if digits == "3":
            return {"outcome": "call_later", "basis": "dtmf"}
        if any(token in normalized for token in ("call me later", "call later", "not now")):
            return {"outcome": "call_later", "basis": "speech"}
        if any(token in normalized for token in ("no", "do not", "don't", "decline", "reject")):
            return {"outcome": "declined", "basis": "speech"}
        affirmative = ("yes", "authorize", "authorise", "go ahead", "contact suppliers")
        if any(token in normalized for token in affirmative) and not any(
            token in normalized for token in ("only rice", "except", "but", "purchase", "order")
        ):
            return {"outcome": "supplier_contact_authorized", "basis": "speech"}
        return {"outcome": "needs_clarification", "basis": "speech"}

    async def _owner_decision(self, transcript: str, digits: str | None) -> dict:
        deterministic = self._deterministic_owner_decision(transcript, digits)
        if deterministic["outcome"] != "needs_clarification" or digits:
            return deterministic
        extracted = await GeminiVoiceService(get_settings()).extract_owner_decision(transcript)
        # The model can clarify a rejection/deferment, but it can never turn an
        # otherwise ambiguous phrase into purchasing or supplier authorization.
        if extracted and extracted["outcome"] in {"declined", "call_later"}:
            return {"outcome": extracted["outcome"], "basis": "gemini_structured"}
        return deterministic

    def _add_turn(
        self, conversation: VoiceConversation, speaker: str, transcript: str, structured: dict
    ) -> None:
        self.session.add(
            VoiceConversationTurn(
                conversation_id=conversation.id,
                speaker=speaker,
                transcript=transcript,
                structured_data=structured,
            )
        )
