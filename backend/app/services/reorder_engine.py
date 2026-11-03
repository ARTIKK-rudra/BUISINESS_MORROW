from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Business,
    Forecast,
    Inventory,
    OutboxEvent,
    Purchase,
    PurchaseItem,
    Recipe,
    RecipeIngredient,
    Recommendation,
    Supplier,
    SupplierProduct,
)
from app.services.audit import add_audit_entry
from app.services.supplier_intelligence import SupplierIntelligenceService


class ReorderEngine:
    """Creates explainable reorder proposals from persisted forecasts and procurement history."""

    HIGH_RISK = Decimal("0.75")
    REVIEW_DAYS = 7

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate(self, business_id: UUID, actor_id: UUID, predictions: list[dict]) -> int:
        supplier_data = await SupplierIntelligenceService(self.session).list(business_id)
        offer_metrics = {
            row["supplier_product_id"]: row
            for supplier in supplier_data
            for row in supplier["offers"]
        }
        created = 0
        today = date.today()
        forecasts = list(
            await self.session.scalars(
                select(Forecast).where(
                    Forecast.business_id == business_id,
                    Forecast.target_type == "product",
                    Forecast.period_start >= today,
                )
            )
        )
        business = await self.session.get(Business, business_id)
        if business is None:
            return 0
        recipes = list(
            await self.session.execute(
                select(
                    Recipe.product_id,
                    Recipe.yield_quantity,
                    RecipeIngredient.ingredient_id,
                    RecipeIngredient.quantity,
                )
                .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
                .where(Recipe.business_id == business_id)
            )
        )
        links: dict[UUID, list[tuple[UUID, Decimal]]] = {}
        for product_id, yield_qty, ingredient_id, ingredient_qty in recipes:
            links.setdefault(ingredient_id, []).append(
                (product_id, Decimal(ingredient_qty) / Decimal(yield_qty))
            )

        for prediction in predictions:
            risk = Decimal(str(prediction.get("stockout_probability") or 0))
            stock_id = prediction.get("inventory_id")
            stock = await self.session.get(Inventory, stock_id)
            if stock is None:
                continue
            stock_item_id = stock.product_id or stock.ingredient_id
            if stock_item_id is None:
                continue
            factors = (
                [(stock.product_id, Decimal(1))]
                if stock.product_id
                else links.get(stock.ingredient_id, [])
            )
            if not factors:
                continue
            supplier_rows = list(
                await self.session.execute(
                    select(SupplierProduct, Supplier)
                    .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
                    .where(
                        SupplierProduct.business_id == business_id,
                        Supplier.is_active.is_(True),
                        SupplierProduct.currency == business.base_currency,
                        (SupplierProduct.product_id == stock_item_id)
                        if stock.product_id
                        else (SupplierProduct.ingredient_id == stock_item_id),
                    )
                )
            )
            if not supplier_rows:
                continue
            demand_by_day: dict[date, Decimal] = {}
            uncertainty_by_day: dict[date, Decimal] = {}
            forecast_versions: set[str] = set()
            for product_id, factor in factors:
                for forecast in forecasts:
                    if forecast.target_id == str(
                        product_id
                    ) and forecast.period_start <= today + timedelta(days=60):
                        demand_by_day[forecast.period_start] = (
                            demand_by_day.get(forecast.period_start, Decimal(0))
                            + Decimal(forecast.point_value) * factor
                        )
                        interval_width = max(
                            Decimal(forecast.upper_value or forecast.point_value)
                            - Decimal(forecast.point_value),
                            Decimal(0),
                        )
                        uncertainty_by_day[forecast.period_start] = (
                            uncertainty_by_day.get(forecast.period_start, Decimal(0))
                            + interval_width * factor
                        )
                        forecast_versions.add(forecast.model_version)
            if not demand_by_day:
                continue
            outstanding_query = (
                select(func.sum(PurchaseItem.quantity - PurchaseItem.received_quantity))
                .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
                .where(
                    Purchase.business_id == business_id,
                    Purchase.status.in_({"ordered", "partially_received"}),
                )
            )
            outstanding_query = outstanding_query.where(
                PurchaseItem.product_id == stock.product_id
                if stock.product_id
                else PurchaseItem.ingredient_id == stock.ingredient_id
            )
            outstanding = Decimal(await self.session.scalar(outstanding_query) or 0)
            position = Decimal(stock.quantity) + outstanding
            choices = []
            for offer, supplier in supplier_rows:
                if offer.unit_cost <= 0:
                    continue
                metric = offer_metrics.get(offer.id, {})
                lead = max(offer.lead_time_days, 0)
                relevant = sorted(
                    day
                    for day in demand_by_day
                    if day <= today + timedelta(days=lead + self.REVIEW_DAYS)
                )
                point_demand = sum((demand_by_day[day] for day in relevant), Decimal(0))
                uncertainty_allowance = sum(
                    (uncertainty_by_day.get(day, Decimal(0)) for day in relevant), Decimal(0)
                )
                demand = point_demand + uncertainty_allowance
                quantity = max(demand + Decimal(stock.safety_stock) - position, Decimal(0))
                if quantity <= 0:
                    continue
                quantity = max(quantity, Decimal(offer.minimum_order_quantity))
                volatility = metric.get("price_change_percent")
                on_time = (
                    (
                        Decimal(metric["on_time_line_count"])
                        / Decimal(metric["reliability_observation_count"])
                    )
                    if metric.get("reliability_observation_count")
                    else None
                )
                # Deterministic ranking uses actual history when available.
                # Unknown reliability only has a neutral ranking prior.
                score = (on_time if on_time is not None else Decimal("0.5")) * Decimal("0.45")
                score += Decimal(1) / Decimal(1 + lead) * Decimal("0.25")
                score += Decimal(1) / (Decimal(1) + offer.unit_cost) * Decimal("0.25")
                score += (
                    Decimal(1)
                    / (Decimal(1) + abs(volatility or Decimal(0)) / Decimal(100))
                    * Decimal("0.05")
                )
                choices.append(
                    (
                        score,
                        offer,
                        supplier,
                        metric,
                        quantity,
                        demand,
                        on_time,
                        uncertainty_allowance,
                    )
                )
            if not choices:
                continue
            _, offer, supplier, metric, quantity, demand, on_time, uncertainty_allowance = max(
                choices, key=lambda row: (row[0], -row[1].unit_cost, -row[1].lead_time_days)
            )
            lead = offer.lead_time_days
            projected_stockout = today
            running = Decimal(stock.quantity)
            for day in sorted(demand_by_day):
                running -= demand_by_day[day]
                if running <= 0:
                    projected_stockout = day
                    break
            recommended_date = max(today, projected_stockout - timedelta(days=lead))
            expected_cost = (quantity * offer.unit_cost).quantize(Decimal("0.01"))
            risk_state = (
                "high"
                if risk >= self.HIGH_RISK
                else "elevated"
                if risk >= Decimal("0.5")
                else "below_threshold"
            )
            reliability_text = (
                "recorded on-time delivery is "
                f"{(on_time * Decimal(100)).quantize(Decimal('0.1'))}% across "
                f"{metric.get('reliability_observation_count', 0)} promised-date lines"
                if on_time is not None
                else (
                    "delivery reliability is unknown because no fully received "
                    "purchase lines are recorded"
                )
            )
            price_change = metric.get("price_change_percent")
            price_text = (
                f"price changed {price_change}% across "
                f"{metric.get('price_observations', 0)} recorded observations"
                if price_change is not None
                else "price movement history is insufficient"
            )
            reason = (
                f"Forecast demand through {lead}-day lead time and a {self.REVIEW_DAYS}-day "
                f"review window, including interval allowance, is {demand.normalize()} units. "
                f"Stock position after open orders is {position.normalize()} units, with "
                f"{Decimal(stock.safety_stock).normalize()} safety stock. {supplier.name} is "
                f"the highest ranked active catalog offer at {offer.unit_cost} {offer.currency}, "
                f"with {lead}-day lead time; {reliability_text}; {price_text}. "
                f"Estimated cost is {expected_cost} {offer.currency}."
            )
            provenance = {
                "source": "forecast_reorder_engine",
                "forecast_model_versions": sorted(forecast_versions),
                "stockout_probability": str(risk),
                "stockout_risk_band": risk_state,
                "high_risk_notification_threshold": str(self.HIGH_RISK),
                "recommended_supplier_id": str(supplier.id),
                "supplier_product_id": str(offer.id),
                "supplier_reliability": str(on_time) if on_time is not None else None,
                "reliability_observations": metric.get("reliability_observation_count", 0),
                "supplier_history": {
                    "purchase_count": metric.get("purchase_count", 0),
                    "price_change_percent": str(metric["price_change_percent"])
                    if metric.get("price_change_percent") is not None
                    else None,
                    "price_observations": metric.get("price_observations", 0),
                    "availability_means": "active catalog offer; physical stock is unverified",
                },
                "recommended_quantity": str(quantity),
                "recommended_date": recommended_date.isoformat(),
                "expected_cost": str(expected_cost),
                "currency": offer.currency,
                "unit_cost": str(offer.unit_cost),
                "supplier_lead_time_days": lead,
                "forecast_demand_window": str(demand),
                "inventory_on_hand": str(stock.quantity),
                "uncertainty_allowance_from_forecast_upper_intervals": str(uncertainty_allowance),
                "outstanding_purchase_quantity": str(outstanding),
                "safety_stock": str(stock.safety_stock),
                "demand_uncertainty": (
                    "Forecast upper-minus-point intervals are summed as a conservative "
                    "order buffer; interval coverage is empirical, not a calibrated guarantee."
                ),
                "ranking_weights": {
                    "delivery_reliability": "0.45",
                    "lead_time": "0.25",
                    "unit_cost": "0.25",
                    "price_stability": "0.05",
                    "unknown reliability prior": (
                        "neutral 0.5 for ranking only; not reported as measured reliability"
                    ),
                },
            }
            pending_rows = list(
                await self.session.scalars(
                    select(Recommendation)
                    .where(
                        Recommendation.business_id == business_id,
                        Recommendation.recommendation_type == "reorder",
                        Recommendation.target_type == "inventory",
                        Recommendation.target_id == str(stock.id),
                        Recommendation.status == "pending",
                    )
                    .order_by(Recommendation.id.desc())
                )
            )
            current = next(
                (
                    row
                    for row in pending_rows
                    if (row.provenance or {}).get("source") == "forecast_reorder_engine"
                ),
                None,
            )
            summary = f"Reorder {quantity.normalize()} units of stock from {supplier.name}"
            if current:
                current.summary, current.rationale, current.provenance = summary, reason, provenance
                recommendation = current
            else:
                recommendation = Recommendation(
                    business_id=business_id,
                    recommendation_type="reorder",
                    target_type="inventory",
                    target_id=str(stock.id),
                    summary=summary[:300],
                    rationale=reason,
                    status="pending",
                    provenance=provenance,
                )
                self.session.add(recommendation)
                await self.session.flush()
                created += 1
            self.session.add(
                OutboxEvent(
                    business_id=business_id,
                    event_type="REORDER_RECOMMENDED",
                    schema_version=1,
                    aggregate_type="recommendation",
                    aggregate_id=str(recommendation.id),
                    payload={
                        "recommendation_id": str(recommendation.id),
                        "inventory_id": str(stock.id),
                        "summary": summary,
                        "stockout_probability": str(risk),
                        "severity": "critical" if risk >= self.HIGH_RISK else "review",
                        "recommended_supplier": supplier.name,
                        "quantity": str(quantity),
                        "recommended_date": recommended_date.isoformat(),
                        "expected_cost": str(expected_cost),
                        "currency": offer.currency,
                    },
                )
            )
            if risk >= self.HIGH_RISK:
                self.session.add(
                    OutboxEvent(
                        business_id=business_id,
                        event_type="STOCK_CRITICAL",
                        schema_version=1,
                        aggregate_type="inventory",
                        aggregate_id=str(stock.id),
                        payload={
                            "inventory_id": str(stock.id),
                            "recommendation_id": str(recommendation.id),
                            "summary": f"High stock-out risk for the next {lead} days. {summary}.",
                            "severity": "critical",
                            "stockout_probability": str(risk),
                        },
                    )
                )
        if created:
            add_audit_entry(
                self.session,
                business_id=business_id,
                actor_user_id=actor_id,
                action="recommendation.forecast_reorder_generated",
                entity_type="business",
                entity_id=business_id,
                metadata={"created": created},
            )
        return created
