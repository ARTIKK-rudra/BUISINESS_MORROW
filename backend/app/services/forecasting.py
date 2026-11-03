from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import sqrt
from pathlib import Path
from statistics import NormalDist
from uuid import UUID

import joblib
import sklearn
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Forecast,
    Inventory,
    ModelVersion,
    Order,
    OrderItem,
    OutboxEvent,
    Prediction,
    Product,
    Recipe,
    RecipeIngredient,
    SupplierProduct,
)
from app.ml.demand import (
    FEATURE_NAMES,
    MODEL_TYPE,
    DemandBundle,
    evaluate_and_fit,
    predict_horizon,
    top_factors,
)
from app.schemas.ml import ForecastGenerateRequest
from app.services.audit import add_audit_entry
from app.services.reorder_engine import ReorderEngine


def artifact_directory() -> Path:
    path = Path(os.getenv("ML_ARTIFACT_DIR", get_settings().ml_artifact_dir)).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def stockout_probability(
    on_hand: float, expected_demand: float, standard_deviation: float
) -> float:
    if standard_deviation <= 0:
        return float(expected_demand >= on_hand)
    z_score = (on_hand - expected_demand) / standard_deviation
    return 1.0 - NormalDist().cdf(z_score)


class ForecastingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_forecasts(
        self, business_id: UUID, product_id: UUID | None = None, limit: int = 500
    ) -> list[Forecast]:
        query = select(Forecast).where(Forecast.business_id == business_id)
        if product_id:
            query = query.where(
                Forecast.target_type == "product", Forecast.target_id == str(product_id)
            )
        return list(
            await self.session.scalars(query.order_by(Forecast.period_start.desc()).limit(limit))
        )

    async def train(self, business_id: UUID, actor_id: UUID | None, product_id: UUID) -> dict:
        product = await self.session.scalar(
            select(Product).where(Product.id == product_id, Product.business_id == business_id)
        )
        if product is None:
            raise NotFoundError("Product not found")
        daily = await self.session.execute(
            select(func.date(Order.placed_at), func.sum(OrderItem.quantity))
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(
                Order.business_id == business_id,
                Order.status == "completed",
                OrderItem.product_id == product_id,
            )
            .group_by(func.date(Order.placed_at))
            .order_by(func.date(Order.placed_at))
        )
        rows = list(daily)
        if len(rows) < 2:
            return {
                "product_id": product_id,
                "dataset_kind": "real_business_transactions",
                "observations": len(rows),
                "evaluations": [],
                "selected_model_version": None,
                "status": "insufficient_data",
                "message": (
                    "At least 2 distinct sales dates are required to construct a demand series."
                ),
            }
        daily_values = {date.fromisoformat(str(day)): float(quantity) for day, quantity in rows}
        first_day, last_day = min(daily_values), max(daily_values)
        values = [
            daily_values.get(first_day + timedelta(days=offset), 0.0)
            for offset in range((last_day - first_day).days + 1)
        ]
        result = await asyncio.to_thread(evaluate_and_fit, values, first_day)
        if result["status"] != "ready":
            return {
                "product_id": product_id,
                "dataset_kind": "real_business_transactions",
                "observations": result["observations"],
                "evaluations": [],
                "selected_model_version": None,
                "status": result["status"],
                "message": (
                    f"Need at least {result['minimum_supervised_rows']} supervised rows "
                    "after the 28-day lag warm-up; no model was selected."
                ),
            }
        bundle: DemandBundle = result["bundle"]
        trained_at = datetime.now(UTC)
        stamp = trained_at.strftime("%Y%m%dT%H%M%S%fZ")
        selected_name = result["selected_model"]
        persisted_versions: list[ModelVersion] = []
        artifact_uri = None
        if selected_name == "random_forest_lag_features":
            artifact_path = (
                artifact_directory() / f"{business_id}-{product_id}-{stamp}-demand.joblib"
            )
            joblib.dump(bundle.estimator, artifact_path)
            artifact_uri = str(artifact_path)
        previous_versions = list(
            await self.session.scalars(
                select(ModelVersion).where(
                    ModelVersion.business_id == business_id,
                    ModelVersion.model_type == MODEL_TYPE,
                    ModelVersion.status == "selected",
                )
            )
        )
        for previous in previous_versions:
            if (previous.metadata_json or {}).get("product_id") == str(product_id):
                previous.status = "superseded"
        for evaluation in result["evaluations"]:
            candidate = evaluation["model"]
            model_version = ModelVersion(
                business_id=business_id,
                model_type=MODEL_TYPE,
                version=f"{candidate}-{stamp}",
                status="selected" if candidate == selected_name else "evaluated",
                dataset_kind="real_business_transactions",
                training_rows=result["supervised_rows"] - evaluation["holdout_days"],
                feature_names=FEATURE_NAMES
                if candidate == "random_forest_lag_features"
                else ["lag_1", "lag_7"],
                metrics={key: value for key, value in evaluation.items() if key != "model"},
                metadata_json={
                    "product_id": str(product_id),
                    "selected_model": selected_name,
                    "residual_quantiles_10_90": [bundle.residual_low, bundle.residual_high]
                    if candidate == selected_name
                    else None,
                    "feature_importance": bundle.feature_importance
                    if candidate == selected_name
                    else None,
                    "holdout_start": result["holdout_start"],
                    "holdout_end": result["holdout_end"],
                    "training_data_start": first_day.isoformat(),
                    "training_data_end": last_day.isoformat(),
                    "feature_schema_version": "demand_features_v1",
                    "temporal_validation": True,
                    "library": "scikit-learn"
                    if candidate == "random_forest_lag_features"
                    else "native baseline",
                    "library_version": sklearn.__version__
                    if candidate == "random_forest_lag_features"
                    else None,
                    "hyperparameters": {
                        "n_estimators": 250,
                        "max_depth": 8,
                        "min_samples_leaf": 2,
                        "random_state": 42,
                    }
                    if candidate == "random_forest_lag_features"
                    else None,
                    "label": (
                        "Observed historical sales; stockout-censored demand may be understated."
                    ),
                },
                artifact_uri=artifact_uri if candidate == selected_name else None,
                trained_at=trained_at,
                evaluated_at=trained_at,
            )
            persisted_versions.append(model_version)
        self.session.add_all(persisted_versions)
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="ml.demand_model_trained",
            entity_type="product",
            entity_id=product_id,
            metadata={"selected_model": selected_name, "observations": len(values)},
        )
        await self.session.commit()
        return {
            "product_id": product_id,
            "dataset_kind": "real_business_transactions",
            "observations": len(values),
            "evaluations": result["evaluations"],
            "selected_model_version": next(
                item.version for item in persisted_versions if item.status == "selected"
            ),
            "status": "evaluated",
            "message": (
                "Measured temporal holdout metrics; these describe this product and period only."
            ),
        }

    async def generate(
        self, business_id: UUID, actor_id: UUID, request: ForecastGenerateRequest
    ) -> list[Forecast]:
        model = await self._latest_selected_model(business_id, request.product_id)
        if model is None:
            raise ConflictError("Train and evaluate a demand model for this product first")
        values, first_day = await self._history(business_id, request.product_id)
        if len(values) < 28:
            raise ConflictError("At least 28 consecutive days of sales history are required")
        selected_name = str(model.metadata_json["selected_model"])
        residual_low, residual_high = model.metadata_json["residual_quantiles_10_90"]
        estimator = joblib.load(model.artifact_uri) if model.artifact_uri else None
        bundle = DemandBundle(
            estimator=estimator,
            residual_low=float(residual_low),
            residual_high=float(residual_high),
            metrics=model.metrics or {},
            feature_importance=model.metadata_json.get("feature_importance") or {},
        )
        rows = await asyncio.to_thread(
            predict_horizon,
            bundle,
            values,
            first_day,
            request.horizon_days,
            selected_name,
        )
        generated_at = datetime.now(UTC)
        forecasts: list[Forecast] = []
        for row in rows:
            forecast = Forecast(
                business_id=business_id,
                target_type="product",
                target_id=str(request.product_id),
                period_start=row["day"],
                period_end=row["day"],
                point_value=Decimal(str(row["point"])).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                ),
                lower_value=Decimal(str(row["low"])).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                ),
                upper_value=Decimal(str(row["high"])).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                ),
                model_version=model.version,
                provenance={
                    "important_factors": top_factors(bundle),
                    "uncertainty": {
                        "method": "temporal_holdout_residual_quantiles",
                        "coverage_target": (
                            "empirical 80 percent residual interval; not calibrated guarantee"
                        ),
                        "lower_residual_quantile": residual_low,
                        "upper_residual_quantile": residual_high,
                    },
                    "evaluation_metrics": model.metrics,
                    "dataset_kind": model.dataset_kind,
                    "input_cutoff": (model.metadata_json or {}).get("training_data_end"),
                },
                generated_at=generated_at,
            )
            forecasts.append(forecast)
        self.session.add_all(forecasts)
        self.session.add(
            OutboxEvent(
                business_id=business_id,
                event_type="FORECAST_UPDATED",
                schema_version=1,
                aggregate_type="product_forecast",
                aggregate_id=str(request.product_id),
                payload={
                    "product_id": str(request.product_id),
                    "model_version": model.version,
                    "horizon_days": request.horizon_days,
                },
            )
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="forecast.generated",
            entity_type="product",
            entity_id=request.product_id,
            metadata={"model_version": model.version, "horizon_days": request.horizon_days},
        )
        await self.session.commit()
        return forecasts

    async def _history(self, business_id: UUID, product_id: UUID) -> tuple[list[float], date]:
        rows = list(
            await self.session.execute(
                select(func.date(Order.placed_at), func.sum(OrderItem.quantity))
                .join(OrderItem, OrderItem.order_id == Order.id)
                .where(
                    Order.business_id == business_id,
                    Order.status == "completed",
                    OrderItem.product_id == product_id,
                )
                .group_by(func.date(Order.placed_at))
                .order_by(func.date(Order.placed_at))
            )
        )
        if not rows:
            return [], date.today()
        daily_values = {date.fromisoformat(str(day)): float(qty) for day, qty in rows}
        first, last = min(daily_values), max(daily_values)
        last = max(last, date.today())
        return (
            [
                daily_values.get(first + timedelta(days=i), 0.0)
                for i in range((last - first).days + 1)
            ],
            first,
        )

    async def _latest_selected_model(
        self, business_id: UUID, product_id: UUID
    ) -> ModelVersion | None:
        rows = list(
            await self.session.scalars(
                select(ModelVersion)
                .where(
                    ModelVersion.business_id == business_id,
                    ModelVersion.model_type == MODEL_TYPE,
                    ModelVersion.status == "selected",
                )
                .order_by(ModelVersion.trained_at.desc())
            )
        )
        return next(
            (row for row in rows if (row.metadata_json or {}).get("product_id") == str(product_id)),
            None,
        )

    async def predict_stockout(self, business_id: UUID, actor_id: UUID) -> list[dict]:
        inventory_rows = list(
            await self.session.scalars(
                select(Inventory).where(
                    Inventory.business_id == business_id, Inventory.quantity >= 0
                )
            )
        )
        if not inventory_rows:
            return []
        today = date.today()
        generated_at = datetime.now(UTC)
        forecast_rows = list(
            await self.session.scalars(
                select(Forecast)
                .where(
                    Forecast.business_id == business_id,
                    Forecast.target_type == "product",
                    Forecast.period_start >= today,
                )
                .order_by(Forecast.generated_at.desc())
            )
        )
        forecasts: dict[tuple[str, date], Forecast] = {}
        for item in forecast_rows:
            forecasts.setdefault((item.target_id, item.period_start), item)
        recipe_links = list(
            await self.session.execute(
                select(
                    RecipeIngredient.ingredient_id,
                    Recipe.product_id,
                    Recipe.yield_quantity,
                    RecipeIngredient.quantity,
                )
                .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
                .where(Recipe.business_id == business_id)
            )
        )
        ingredient_recipes: dict[UUID, list[tuple[UUID, Decimal]]] = {}
        for ingredient_id, product_id, yield_quantity, ingredient_quantity in recipe_links:
            ingredient_recipes.setdefault(ingredient_id, []).append(
                (product_id, Decimal(ingredient_quantity) / Decimal(yield_quantity))
            )
        output: list[dict] = []
        stockout_model = await self.session.scalar(
            select(ModelVersion).where(
                ModelVersion.business_id == business_id,
                ModelVersion.model_type == "stockout_risk",
                ModelVersion.version == "forecast_aggregation_v1",
            )
        )
        if stockout_model is None:
            self.session.add(
                ModelVersion(
                    business_id=business_id,
                    model_type="stockout_risk",
                    version="forecast_aggregation_v1",
                    status="active",
                    dataset_kind="real_inventory_and_forecasts",
                    training_rows=0,
                    feature_names=[
                        "on_hand",
                        "forecast_demand",
                        "forecast_uncertainty",
                        "supplier_lead_time",
                    ],
                    metrics=None,
                    metadata_json={
                        "method": "normal approximation of summed forecast intervals",
                        "calibrated": False,
                    },
                    trained_at=datetime.now(UTC),
                )
            )
        for stock in inventory_rows:
            if stock.product_id:
                recipe_factor = [(stock.product_id, Decimal("1"))]
                item_id = stock.product_id
                item_type = "product"
            else:
                item_id = stock.ingredient_id
                item_type = "ingredient"
                recipe_factor = ingredient_recipes.get(item_id, [])
            if not recipe_factor:
                continue
            links = await self.session.scalars(
                select(SupplierProduct).where(
                    SupplierProduct.business_id == business_id,
                    or_(
                        SupplierProduct.product_id == item_id,
                        SupplierProduct.ingredient_id == item_id,
                    ),
                )
            )
            lead_days = max((row.lead_time_days for row in links), default=0)
            per_day: dict[date, tuple[float, float]] = {}
            for product_id, factor in recipe_factor:
                for (target_id, forecast_day), forecast in forecasts.items():
                    if target_id != str(product_id):
                        continue
                    point = float(forecast.point_value) * float(factor)
                    low = float(forecast.lower_value or forecast.point_value) * float(factor)
                    high = float(forecast.upper_value or forecast.point_value) * float(factor)
                    old_point, old_variance = per_day.get(forecast_day, (0.0, 0.0))
                    # Convert the central interval to an approximate standard deviation.
                    sigma = max(0.0, (high - low) / (2 * 1.28155))
                    per_day[forecast_day] = (old_point + point, old_variance + sigma**2)
            if not per_day:
                continue
            ordered_days = sorted(per_day)
            available = float(stock.quantity)
            cumulative = 0.0
            expected_stockout_date = today.isoformat() if available <= 0 else None
            if available > 0:
                for forecast_day in ordered_days:
                    cumulative += per_day[forecast_day][0]
                    if cumulative >= available:
                        expected_stockout_date = forecast_day.isoformat()
                        break
            coverage = [day for day in ordered_days if (day - today).days < max(lead_days, 1)]
            if len(coverage) < lead_days:
                continue
            expected_during_lead = sum(per_day[day][0] for day in coverage)
            standard_deviation = sqrt(sum(per_day[day][1] for day in coverage))
            probability = stockout_probability(available, expected_during_lead, standard_deviation)
            expected_days_remaining = (
                0
                if available <= 0
                else next(
                    (
                        (day - today).days
                        for day in ordered_days
                        if day.isoformat() == expected_stockout_date
                    ),
                    None,
                )
            )
            prediction = {
                "inventory_id": stock.id,
                "item_id": item_id,
                "item_type": item_type,
                "on_hand": stock.quantity,
                "supplier_lead_time_days": lead_days,
                "expected_demand_during_lead_time": round(expected_during_lead, 3),
                "expected_stockout_date": expected_stockout_date,
                "remaining_stock_days": expected_days_remaining,
                "stockout_probability": round(probability, 5),
                "generated_at": generated_at,
                "important_factors": [
                    "on_hand",
                    "forecast demand through lead time",
                    "forecast interval width",
                    "supplier lead time",
                ],
                "uncertainty": (
                    "Normal approximation; assumes independent daily forecast errors "
                    "and is not calibrated."
                ),
                "model_version": "forecast_aggregation_v1",
            }
            output.append(prediction)
            self.session.add(
                Prediction(
                    business_id=business_id,
                    prediction_type="stockout_risk",
                    target_type="inventory",
                    target_id=str(stock.id),
                    predicted_value=Decimal(str(expected_days_remaining))
                    if expected_days_remaining is not None
                    else None,
                    probability=Decimal(str(probability)).quantize(Decimal("0.00001")),
                    model_version="forecast_aggregation_v1",
                    provenance=jsonable_encoder(prediction),
                )
            )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="prediction.stockout_generated",
            entity_type="business",
            entity_id=business_id,
            metadata={"prediction_count": len(output)},
        )
        await ReorderEngine(self.session).generate(business_id, actor_id, output)
        await self.session.commit()
        return output
