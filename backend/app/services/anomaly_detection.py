from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from math import log1p
from uuid import UUID

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Anomaly,
    InventoryMovement,
    ModelVersion,
    Order,
    OrderItem,
    OutboxEvent,
    Payment,
    Refund,
    SupplierPriceHistory,
    SupplierProduct,
)
from app.services.audit import add_audit_entry
from app.services.forecasting import artifact_directory

MIN_ANOMALY_ROWS = 20


def fit_isolation_forest(rows: list[dict]) -> tuple[list[dict], IsolationForest, RobustScaler]:
    feature_names = rows[0]["feature_names"]
    matrix = np.asarray([row["features"] for row in rows], dtype=float)
    scaler = RobustScaler(quantile_range=(10, 90))
    transformed = scaler.fit_transform(matrix)
    model = IsolationForest(
        n_estimators=250,
        contamination="auto",
        random_state=42,
        n_jobs=1,
    )
    model.fit(transformed)
    labels = model.predict(transformed)
    decisions = model.decision_function(transformed)
    explanations = []
    for index, row in enumerate(rows):
        if labels[index] != -1:
            continue
        values = matrix[index]
        medians = np.median(matrix, axis=0)
        deviations = np.median(np.abs(matrix - medians), axis=0)
        deviations = np.where(deviations == 0, np.std(matrix, axis=0) + 1e-9, deviations)
        importance = np.abs(values - medians) / deviations
        factors = [
            {
                "feature": feature_names[f_index],
                "observed_value": float(values[f_index]),
                "robust_deviation": float(importance[f_index]),
            }
            for f_index in np.argsort(importance)[::-1][:3]
        ]
        explanations.append(
            {
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "score": float(max(0.0, -decisions[index])),
                "important_factors": factors,
                "method": "IsolationForest; unsupervised review signal, not a confirmed error",
            }
        )
    return explanations, model, scaler


class AnomalyDetectionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, business_id: UUID, limit: int = 100) -> list[Anomaly]:
        return list(
            await self.session.scalars(
                select(Anomaly)
                .where(Anomaly.business_id == business_id)
                .order_by(Anomaly.created_at.desc())
                .limit(limit)
            )
        )

    async def detect(self, business_id: UUID, actor_id: UUID) -> dict:
        datasets: dict[str, list[dict]] = {
            "sales": [],
            "refunds": [],
            "inventory_movements": [],
            "supplier_prices": [],
        }
        skipped: dict[str, str] = {}

        order_rows = list(
            await self.session.execute(
                select(
                    Order.id,
                    Order.total,
                    Order.discount,
                    Order.subtotal,
                    func.count(OrderItem.id),
                )
                .join(OrderItem, OrderItem.order_id == Order.id)
                .where(Order.business_id == business_id, Order.status == "completed")
                .group_by(Order.id)
                .order_by(Order.placed_at.desc())
                .limit(5000)
            )
        )
        datasets["sales"] = [
            {
                "entity_type": "sale",
                "entity_id": str(row.id),
                "features": [
                    log1p(float(row.total)),
                    float(row.discount / row.subtotal) if row.subtotal else 0.0,
                    float(row[4]),
                ],
                "feature_names": ["log_total", "discount_rate", "item_count"],
            }
            for row in order_rows
        ]

        refund_rows = list(
            await self.session.execute(
                select(Refund.id, Refund.amount, Payment.amount)
                .join(Payment, Payment.id == Refund.payment_id)
                .where(Refund.business_id == business_id, Refund.status == "completed")
                .order_by(Refund.created_at.desc())
                .limit(5000)
            )
        )
        datasets["refunds"] = [
            {
                "entity_type": "refund",
                "entity_id": str(row.id),
                "features": [
                    log1p(float(row.amount)),
                    float(row.amount / row[2]) if row[2] else 0.0,
                ],
                "feature_names": ["log_amount", "payment_fraction"],
            }
            for row in refund_rows
        ]

        movement_rows = list(
            await self.session.scalars(
                select(InventoryMovement)
                .where(InventoryMovement.business_id == business_id)
                .order_by(InventoryMovement.created_at.desc())
                .limit(20000)
            )
        )
        by_inventory: dict[UUID, list[InventoryMovement]] = {}
        for movement in movement_rows:
            by_inventory.setdefault(movement.inventory_id, []).append(movement)
        for inventory_id, group in by_inventory.items():
            datasets[f"inventory_movements:{inventory_id}"] = [
                {
                    "entity_type": "inventory_movement",
                    "entity_id": str(row.id),
                    "features": [
                        log1p(abs(float(row.quantity_delta))),
                        float(row.quantity_delta < 0),
                    ],
                    "feature_names": ["log_abs_quantity_delta", "is_decrease"],
                }
                for row in group
            ]

        prices = list(
            await self.session.scalars(
                select(SupplierPriceHistory)
                .join(
                    SupplierProduct, SupplierProduct.id == SupplierPriceHistory.supplier_product_id
                )
                .where(SupplierProduct.business_id == business_id)
                .order_by(SupplierPriceHistory.effective_at.desc())
                .limit(20000)
            )
        )
        by_supplier_item: dict[UUID, list[SupplierPriceHistory]] = {}
        for price in prices:
            by_supplier_item.setdefault(price.supplier_product_id, []).append(price)
        for supplier_item_id, group in by_supplier_item.items():
            ordered = sorted(group, key=lambda row: row.effective_at)
            records = []
            previous = None
            for row in ordered:
                current = float(row.unit_cost)
                change = (current - previous) / previous if previous else 0.0
                records.append(
                    {
                        "entity_type": "supplier_price",
                        "entity_id": str(row.id),
                        "features": [log1p(current), change],
                        "feature_names": ["log_unit_cost", "relative_price_change"],
                    }
                )
                previous = current
            datasets[f"supplier_prices:{supplier_item_id}"] = records

        inspected = {name: len(rows) for name, rows in datasets.items()}
        detected_count = 0
        for dataset_name, rows in datasets.items():
            if len(rows) < MIN_ANOMALY_ROWS:
                skipped[dataset_name] = (
                    f"Need at least {MIN_ANOMALY_ROWS} records; found {len(rows)}."
                )
                continue
            explanations, model, scaler = await asyncio.to_thread(fit_isolation_forest, rows)
            timestamp = datetime.now(UTC)
            model_type = f"anomaly_{dataset_name.split(':', 1)[0]}"
            version = f"isolation_forest_v1_{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}"
            scope_slug = dataset_name.split(":", 1)[-1]
            artifact_path = artifact_directory() / (
                f"{business_id}-{model_type}-{scope_slug}-"
                f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}.joblib"
            )
            await asyncio.to_thread(joblib.dump, {"model": model, "scaler": scaler}, artifact_path)
            self.session.add(
                ModelVersion(
                    business_id=business_id,
                    model_type=model_type,
                    version=version,
                    status="evaluated_unsupervised",
                    dataset_kind="real_business_transactions",
                    training_rows=len(rows),
                    feature_names=rows[0]["feature_names"],
                    metrics={
                        "outlier_count": len(explanations),
                        "evaluation": "No labeled ground truth; accuracy metrics are unavailable.",
                    },
                    metadata_json={
                        "scope": dataset_name,
                        "contamination": "auto",
                        "random_state": 42,
                        "library": "scikit-learn",
                        "library_version": sklearn.__version__,
                        "estimator_parameters": {"n_estimators": 250, "n_jobs": 1},
                    },
                    artifact_uri=str(artifact_path),
                    trained_at=timestamp,
                    evaluated_at=timestamp,
                )
            )
            existing = (
                set(
                    await self.session.scalars(
                        select(Anomaly.entity_id).where(
                            Anomaly.business_id == business_id,
                            Anomaly.entity_type.in_({item["entity_type"] for item in explanations}),
                            Anomaly.status == "open",
                            Anomaly.entity_id.in_({item["entity_id"] for item in explanations}),
                        )
                    )
                )
                if explanations
                else set()
            )
            for item in explanations:
                if item["entity_id"] in existing:
                    continue
                factors = item["important_factors"]
                summary = (
                    f"Unusual {item['entity_type'].replace('_', ' ')} pattern; "
                    "review the contributing values."
                )
                self.session.add(
                    Anomaly(
                        business_id=business_id,
                        entity_type=item["entity_type"],
                        entity_id=item["entity_id"],
                        severity="review",
                        score=item["score"],
                        summary=summary[:300],
                        model_version=version,
                        provenance={
                            "important_factors": factors,
                            "uncertainty": (
                                "Unsupervised score without labeled validation; not a probability."
                            ),
                            "method": item["method"],
                        },
                    )
                )
                self.session.add(
                    OutboxEvent(
                        business_id=business_id,
                        event_type="ANOMALY_DETECTED",
                        schema_version=1,
                        aggregate_type=item["entity_type"],
                        aggregate_id=item["entity_id"],
                        payload={
                            "entity_type": item["entity_type"],
                            "entity_id": item["entity_id"],
                            "model_version": version,
                            "score": item["score"],
                            "severity": "review",
                            "summary": summary[:300],
                        },
                    )
                )
                detected_count += 1
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="ml.anomaly_detection_run",
            entity_type="business",
            entity_id=business_id,
            metadata={"detected_count": detected_count, "inspected": inspected},
        )
        await self.session.commit()
        return {
            "dataset_kind": "real_business_transactions",
            "inspected": inspected,
            "detected": detected_count,
            "skipped": skipped,
        }
