from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Anomaly,
    Business,
    Expense,
    Forecast,
    Ingredient,
    Inventory,
    Order,
    Prediction,
    Product,
    Refund,
    Supplier,
)
from app.services.analytics import AnalyticsService
from app.services.inventory import inventory_level


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


class AssistantService:
    """Closed-set, read-only assistant. Every numeric answer comes from tenant-scoped SQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def answer(self, business_id, question: str) -> dict:
        normalized = " ".join(question.lower().strip().split())
        business = await self.session.get(Business, business_id)
        try:
            zone = ZoneInfo(business.timezone if business else "UTC")
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("UTC")
        today = datetime.now(zone).date()
        if normalized in {"hello", "hi", "hey", "who are you", "what can you do"}:
            return self._answer(
                "capability",
                "I am Morrow, your read-only business assistant. I can report recorded sales, orders, expenses, suppliers, stock levels, forecasts, refund anomalies, and profit and loss. I do not create purchases or change records.",
                [],
            )
        if any(
            term in normalized for term in ("low", "stock", "out of stock", "stock-out", "stockout")
        ):
            rows = list(
                await self.session.scalars(
                    select(Inventory).where(Inventory.business_id == business_id)
                )
            )
            product_ids = [row.product_id for row in rows if row.product_id]
            products = (
                {
                    item.id: item
                    for item in await self.session.scalars(
                        select(Product).where(
                            Product.business_id == business_id, Product.id.in_(product_ids)
                        )
                    )
                }
                if product_ids
                else {}
            )
            ingredient_ids = [row.ingredient_id for row in rows if row.ingredient_id]
            ingredients = (
                {
                    item.id: item
                    for item in await self.session.scalars(
                        select(Ingredient).where(
                            Ingredient.business_id == business_id, Ingredient.id.in_(ingredient_ids)
                        )
                    )
                }
                if ingredient_ids
                else {}
            )
            low = []
            ml_risks = list(
                await self.session.scalars(
                    select(Prediction)
                    .where(
                        Prediction.business_id == business_id,
                        Prediction.prediction_type == "stockout_risk",
                    )
                    .order_by(Prediction.created_at.desc())
                    .limit(20)
                )
            )
            risk_by_target = {}
            for prediction in ml_risks:
                risk_by_target.setdefault(prediction.target_id, prediction)
            for item in rows:
                level = inventory_level(
                    item.quantity, item.reorder_point, item.minimum_stock, item.safety_stock
                )
                ml = risk_by_target.get(str(item.id))
                ml_probability = (
                    Decimal(ml.probability) if ml and ml.probability is not None else None
                )
                if level in {"low", "critical", "out_of_stock"} or (
                    ml_probability is not None and ml_probability >= Decimal("0.5")
                ):
                    target = (
                        products.get(item.product_id)
                        if item.product_id
                        else ingredients.get(item.ingredient_id)
                    )
                    if target:
                        detail = f"{target.name}: {item.quantity} {target.unit}"
                        if level != "healthy":
                            detail += f" (rule-based {level.replace('_', ' ')})"
                        if ml_probability is not None:
                            detail += f", stored ML stock-out probability {ml_probability:.0%}"
                        low.append(detail)
            return self._answer(
                "stock_levels",
                "Current stock risk: "
                + (
                    "; ".join(low)
                    if low
                    else (
                        "no products or ingredients are currently below their "
                        "configured thresholds."
                    )
                ),
                [
                    "inventory",
                    "product and ingredient catalog",
                    "stored ML predictions where available",
                ],
            )
        if "refund" in normalized and any(
            term in normalized for term in ("unusual", "strange", "anomal")
        ):
            anomalies = list(
                await self.session.scalars(
                    select(Anomaly)
                    .where(
                        Anomaly.business_id == business_id,
                        Anomaly.entity_type == "refund",
                        Anomaly.status == "open",
                    )
                    .order_by(Anomaly.created_at.desc())
                    .limit(10)
                )
            )
            if anomalies:
                refunds = {
                    row.id: row
                    for row in await self.session.scalars(
                        select(Refund).where(
                            Refund.business_id == business_id,
                            Refund.id.in_(
                                [
                                    UUID(item.entity_id)
                                    for item in anomalies
                                    if _is_uuid(item.entity_id)
                                ]
                            ),
                        )
                    )
                }
                result = "; ".join(
                    f"{item.summary} (severity {item.severity}, "
                    f"{refunds[UUID(item.entity_id)].amount} "
                    f"{refunds[UUID(item.entity_id)].currency}, "
                    f"{item.created_at:%Y-%m-%d})"
                    if _is_uuid(item.entity_id) and UUID(item.entity_id) in refunds
                    else f"{item.summary} (severity {item.severity}, {item.created_at:%Y-%m-%d})"
                    for item in anomalies
                )
            else:
                count = (
                    await self.session.scalar(
                        select(func.count(Refund.id)).where(Refund.business_id == business_id)
                    )
                    or 0
                )
                result = (
                    f"No refund anomalies are stored. The business has {count} refund records; "
                    "no unusual refunds can be identified from current anomaly records."
                )
            return self._answer("refund_anomalies", result, ["anomalies", "refunds"])
        if "profit" in normalized and any(
            term in normalized for term in ("decrease", "drop", "down", "why", "caused")
        ):
            current_start = today - timedelta(days=6)
            previous_start = current_start - timedelta(days=7)
            reports_now = await AnalyticsService(self.session).profit_and_loss(
                business_id, current_start, today
            )
            reports_before = await AnalyticsService(self.session).profit_and_loss(
                business_id, previous_start, current_start - timedelta(days=1)
            )
            current = {str(r["currency"]): r for r in reports_now}
            previous = {str(r["currency"]): r for r in reports_before}
            if not current and not previous:
                result = (
                    "There are no ledger entries for the last two weeks, "
                    "so I cannot attribute a profit change."
                )
            else:
                chunks = []
                for currency in sorted(set(current) | set(previous)):
                    now, before = current.get(currency, {}), previous.get(currency, {})
                    delta = Decimal(now.get("net_profit", 0)) - Decimal(before.get("net_profit", 0))
                    causes = []
                    for field, label in (
                        ("revenue", "revenue"),
                        ("refunds", "refunds"),
                        ("cost_of_goods_sold", "cost of goods"),
                        ("operating_expenses", "operating expenses"),
                    ):
                        difference = Decimal(now.get(field, 0)) - Decimal(before.get(field, 0))
                        if difference:
                            causes.append(f"{label} {difference:+.2f} {currency}")
                    chunks.append(
                        f"Net profit changed {delta:+.2f} {currency} between "
                        f"{previous_start}–{current_start - timedelta(days=1)} and "
                        f"{current_start}–{today}. Drivers: "
                        f"{', '.join(causes) or 'no component change was found'}."
                    )
                result = " ".join(chunks)
            return self._answer("profit_comparison", result, ["ledger", "profit and loss"])
        if "sales" in normalized and any(
            term in normalized for term in ("today", "today's", "todays", "current day")
        ):
            start = datetime.combine(today, time.min, tzinfo=zone).astimezone(UTC)
            end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
            rows = (
                await self.session.execute(
                    select(Order.currency, func.sum(Order.total), func.count(Order.id))
                    .where(
                        Order.business_id == business_id,
                        Order.placed_at >= start,
                        Order.placed_at < end,
                        Order.status == "completed",
                    )
                    .group_by(Order.currency)
                )
            ).all()
            result = (
                f"No completed sales are recorded for {today}."
                if not rows
                else "; ".join(
                    f"{int(count)} completed orders totaling "
                    f"{Decimal(total or 0):.2f} {currency} on {today}"
                    for currency, total, count in rows
                )
            )
            return self._answer("sales_today", result, ["completed orders"])
        if "expense" in normalized or "spend" in normalized:
            start = datetime.combine(today - timedelta(days=29), time.min, tzinfo=zone).astimezone(UTC)
            rows = (
                await self.session.execute(
                    select(Expense.currency, func.sum(Expense.amount), func.count(Expense.id))
                    .where(Expense.business_id == business_id, Expense.occurred_at >= start)
                    .group_by(Expense.currency)
                )
            ).all()
            result = (
                "No expenses are recorded in the last 30 days."
                if not rows
                else "; ".join(
                    f"{int(count)} expense records totaling {Decimal(total or 0):.2f} {currency} in the last 30 days"
                    for currency, total, count in rows
                )
            )
            return self._answer("expenses", result, ["expenses"])
        if "supplier" in normalized and not any(term in normalized for term in ("order", "buy", "purchase")):
            suppliers = list(
                await self.session.scalars(
                    select(Supplier)
                    .where(Supplier.business_id == business_id, Supplier.is_active.is_(True))
                    .order_by(Supplier.name)
                )
            )
            result = (
                "No active suppliers are recorded."
                if not suppliers
                else f"There are {len(suppliers)} active suppliers: " + ", ".join(item.name for item in suppliers[:10]) + "."
            )
            return self._answer("suppliers", result, ["suppliers"])
        if "order" in normalized and not any(term in normalized for term in ("buy", "purchase", "tomorrow", "rice")):
            rows = (
                await self.session.execute(
                    select(Order.status, func.count(Order.id))
                    .where(Order.business_id == business_id)
                    .group_by(Order.status)
                )
            ).all()
            result = (
                "No orders are recorded."
                if not rows
                else "Recorded orders by status: " + "; ".join(f"{int(count)} {status}" for status, count in rows) + "."
            )
            return self._answer("orders", result, ["orders"])
        if "sales" in normalized and any(
            term in normalized for term in ("compare", "compared", "last week", "week")
        ):
            now = datetime.now(zone)
            start_current = today - timedelta(days=today.weekday())
            start_previous = start_current - timedelta(days=7)
            # Compare matching elapsed days for an in-progress week.
            elapsed = max((today - start_current).days, 0)
            end_previous = start_previous + timedelta(days=elapsed)

            async def sum_sales(start_date, end_date):
                start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC)
                end = datetime.combine(
                    end_date + timedelta(days=1), time.min, tzinfo=zone
                ).astimezone(UTC)
                return (
                    await self.session.execute(
                        select(Order.currency, func.sum(Order.total))
                        .where(
                            Order.business_id == business_id,
                            Order.placed_at >= start,
                            Order.placed_at < end,
                            Order.status == "completed",
                        )
                        .group_by(Order.currency)
                    )
                ).all()

            recent = dict(await sum_sales(start_current, today))
            previous = dict(await sum_sales(start_previous, end_previous))
            currencies = sorted(set(recent) | set(previous))
            result = (
                "No completed sales are recorded in these periods."
                if not currencies
                else "; ".join(
                    f"{currency}: {Decimal(recent.get(currency) or 0):.2f} this week vs "
                    f"{Decimal(previous.get(currency) or 0):.2f} for the same days last week"
                    for currency in currencies
                )
            )
            return self._answer("sales_comparison", result, ["completed orders"])
        if (
            "order" in normalized
            or "buy" in normalized
            or "rice" in normalized
            or "tomorrow" in normalized
        ):
            ingredients = list(
                await self.session.scalars(
                    select(Ingredient).where(
                        Ingredient.business_id == business_id, Ingredient.is_active.is_(True)
                    )
                )
            )
            selected = next(
                (
                    item
                    for item in ingredients
                    if item.name.lower() in normalized
                    or item.name.lower().rstrip("s") in normalized
                ),
                None,
            )
            if selected:
                stock = await self.session.scalar(
                    select(func.sum(Inventory.quantity)).where(
                        Inventory.business_id == business_id, Inventory.ingredient_id == selected.id
                    )
                )
                forecast = await self.session.scalar(
                    select(func.sum(Forecast.point_value)).where(
                        Forecast.business_id == business_id,
                        Forecast.target_type == "ingredient",
                        Forecast.target_id == str(selected.id),
                        Forecast.period_start == today + timedelta(days=1),
                    )
                )
                if forecast is None:
                    result = (
                        f"{selected.name}: current recorded stock is {Decimal(stock or 0)} "
                        f"{selected.unit}. There is no stored forecast for tomorrow, "
                        "so I cannot calculate an order quantity."
                    )
                else:
                    required = max(
                        Decimal(forecast) + selected.safety_stock - Decimal(stock or 0), Decimal(0)
                    )
                    result = (
                        f"{selected.name}: recorded stock is {Decimal(stock or 0)} "
                        f"{selected.unit}; stored demand forecast for tomorrow is "
                        f"{Decimal(forecast)} {selected.unit}. Replenishment to cover "
                        f"that demand plus safety stock is {required} {selected.unit}. "
                        "This is a recommendation only; no purchase was created."
                    )
                return self._answer(
                    "reorder_guidance",
                    result,
                    ["inventory", "ingredient settings", "stored forecast"],
                )
            products = list(
                await self.session.scalars(
                    select(Product).where(
                        Product.business_id == business_id, Product.is_active.is_(True)
                    )
                )
            )
            forecasts = list(
                await self.session.scalars(
                    select(Forecast).where(
                        Forecast.business_id == business_id,
                        Forecast.target_type == "product",
                        Forecast.period_start == today + timedelta(days=1),
                    )
                )
            )
            forecast_by_id = {row.target_id: row for row in forecasts}
            selected_product = next(
                (product for product in products if product.name.lower() in normalized), None
            )
            if selected_product and str(selected_product.id) not in forecast_by_id:
                return self._answer(
                    "reorder_guidance",
                    f"No demand forecast is stored for {selected_product.name} on "
                    f"{today + timedelta(days=1)}. I cannot estimate its order quantity. "
                    "No purchase was created.",
                    ["stored product forecasts"],
                )
            if selected_product:
                products = [selected_product]
            suggestions = []
            for product in products:
                forecast = forecast_by_id.get(str(product.id))
                if forecast is None:
                    continue
                on_hand = await self.session.scalar(
                    select(func.sum(Inventory.quantity)).where(
                        Inventory.business_id == business_id, Inventory.product_id == product.id
                    )
                ) or Decimal(0)
                safety = await self.session.scalar(
                    select(func.sum(Inventory.safety_stock)).where(
                        Inventory.business_id == business_id,
                        Inventory.product_id == product.id,
                    )
                ) or Decimal(0)
                quantity = max(
                    Decimal(forecast.point_value) + Decimal(safety) - Decimal(on_hand),
                    Decimal(0),
                )
                if quantity > 0:
                    suggestions.append(
                        f"{product.name}: forecast {forecast.point_value} {product.unit}, "
                        f"stock {on_hand} {product.unit}, suggested replenishment "
                        f"{quantity} {product.unit}"
                    )
            if suggestions:
                return self._answer(
                    "reorder_guidance",
                    "Stored forecasts suggest: "
                    + "; ".join(suggestions[:10])
                    + ". These are recommendations only; no purchase was created.",
                    ["stored product forecasts", "inventory"],
                )
            if not forecast_by_id:
                return self._answer(
                    "reorder_guidance",
                    f"No product demand forecasts are stored for {today + timedelta(days=1)}. "
                    "I cannot estimate order quantities without a saved forecast. "
                    "No purchase was created.",
                    ["stored product forecasts"],
                )
            return self._answer(
                "reorder_guidance",
                "I need a specific product or ingredient and an available forecast to "
                "calculate an order quantity. No purchase has been created.",
                ["inventory", "stored forecast"],
            )
        return self._answer(
            "unsupported",
            f"I received: “{question.strip()}”. I do not yet have a verified query for that request. "
            "Try asking about sales, orders, expenses, suppliers, current stock, stored forecasts, "
            "refund anomalies, or profit and loss.",
            [],
        )

    @staticmethod
    def _answer(intent: str, answer: str, sources: list[str]) -> dict:
        return {
            "intent": intent,
            "answer": answer,
            "sources": sources,
            "generated_at": datetime.now(UTC),
            "grounded": True,
        }
