from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import cos, pi, sin, sqrt
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

FEATURE_NAMES = [
    "lag_1",
    "lag_7",
    "lag_14",
    "mean_7",
    "mean_28",
    "std_7",
    "weekday_sin",
    "weekday_cos",
    "month_sin",
    "month_cos",
]
MODEL_TYPE = "demand_forecast"
MIN_SUPERVISED_ROWS = 35


@dataclass
class DemandEvaluation:
    name: str
    metrics: dict[str, float]
    residuals: list[float]


@dataclass
class DemandBundle:
    estimator: RandomForestRegressor | None
    residual_low: float
    residual_high: float
    metrics: dict[str, float]
    feature_importance: dict[str, float]


def make_features(values: list[float], target_day: date) -> list[float]:
    if len(values) < 28:
        raise ValueError("At least 28 prior observations are required for demand features")
    return [
        values[-1],
        values[-7],
        values[-14],
        float(np.mean(values[-7:])),
        float(np.mean(values[-28:])),
        float(np.std(values[-7:])),
        sin(2 * pi * target_day.weekday() / 7),
        cos(2 * pi * target_day.weekday() / 7),
        sin(2 * pi * target_day.month / 12),
        cos(2 * pi * target_day.month / 12),
    ]


def supervised(values: list[float], first_day: date) -> tuple[np.ndarray, np.ndarray, list[date]]:
    features: list[list[float]] = []
    targets: list[float] = []
    days: list[date] = []
    for index in range(28, len(values)):
        target_day = first_day + timedelta(days=index)
        features.append(make_features(values[:index], target_day))
        targets.append(values[index])
        days.append(target_day)
    return np.asarray(features, dtype=float), np.asarray(targets, dtype=float), days


def metric_set(actual: list[float], predicted: list[float]) -> dict[str, float]:
    mae = float(mean_absolute_error(actual, predicted))
    rmse = float(sqrt(mean_squared_error(actual, predicted)))
    denominator = [abs(a) + abs(p) for a, p in zip(actual, predicted, strict=True)]
    smape = float(
        np.mean(
            [
                200 * abs(a - p) / d if d else 0.0
                for a, p, d in zip(actual, predicted, denominator, strict=True)
            ]
        )
    )
    nonzero = [(a, p) for a, p in zip(actual, predicted, strict=True) if a != 0]
    result = {"mae": mae, "rmse": rmse, "smape": smape}
    if nonzero:
        result["mape_nonzero_actual_pct"] = float(
            np.mean([100 * abs(a - p) / abs(a) for a, p in nonzero])
        )
    return result


def evaluate_and_fit(values: list[float], first_day: date) -> dict[str, Any]:
    x, y, days = supervised(values, first_day)
    if len(y) < MIN_SUPERVISED_ROWS:
        return {
            "status": "insufficient_data",
            "observations": len(values),
            "supervised_rows": len(y),
            "minimum_supervised_rows": MIN_SUPERVISED_ROWS,
            "evaluations": [],
            "bundle": None,
        }

    holdout_size = max(7, int(round(len(y) * 0.2)))
    split = len(y) - holdout_size
    train_x, test_x = x[:split], x[split:]
    train_y, test_y = y[:split], y[split:]
    test_days = days[split:]
    start_index = 28 + split

    evaluation_records: list[DemandEvaluation] = []
    naive_predictions: list[float] = []
    seasonal_predictions: list[float] = []
    for offset, _actual in enumerate(test_y):
        index = start_index + offset
        naive_predictions.append(values[index - 1])
        seasonal_predictions.append(values[index - 7])
    for name, prediction in (
        ("naive_last_observation", naive_predictions),
        ("seasonal_naive_7_day", seasonal_predictions),
    ):
        evaluation_records.append(
            DemandEvaluation(
                name,
                metric_set(test_y.tolist(), prediction),
                [a - p for a, p in zip(test_y.tolist(), prediction, strict=True)],
            )
        )

    forest = RandomForestRegressor(
        n_estimators=250,
        max_depth=8,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=1,
    )
    forest.fit(train_x, train_y)
    ml_predictions = np.maximum(forest.predict(test_x), 0).tolist()
    evaluation_records.append(
        DemandEvaluation(
            "random_forest_lag_features",
            metric_set(test_y.tolist(), ml_predictions),
            [a - p for a, p in zip(test_y.tolist(), ml_predictions, strict=True)],
        )
    )
    evaluations = [
        {"model": item.name, **item.metrics, "holdout_days": holdout_size}
        for item in evaluation_records
    ]
    best = min(evaluation_records, key=lambda item: item.metrics["smape"])
    if best.name == "random_forest_lag_features":
        selected_model = "random_forest_lag_features"
        residuals = best.residuals
        forest.fit(x, y)
        importances = {
            key: float(value)
            for key, value in zip(FEATURE_NAMES, forest.feature_importances_, strict=True)
        }
        bundle = DemandBundle(
            estimator=forest,
            residual_low=float(np.quantile(residuals, 0.1)),
            residual_high=float(np.quantile(residuals, 0.9)),
            metrics=best.metrics,
            feature_importance=importances,
        )
    else:
        selected_model = best.name
        residuals = best.residuals
        bundle = DemandBundle(
            estimator=None,
            residual_low=float(np.quantile(residuals, 0.1)),
            residual_high=float(np.quantile(residuals, 0.9)),
            metrics=best.metrics,
            feature_importance={},
        )
    return {
        "status": "ready",
        "observations": len(values),
        "supervised_rows": len(y),
        "holdout_start": test_days[0].isoformat(),
        "holdout_end": test_days[-1].isoformat(),
        "evaluations": evaluations,
        "selected_model": selected_model,
        "bundle": bundle,
    }


def predict_horizon(
    bundle: DemandBundle,
    values: list[float],
    first_day: date,
    horizon: int,
    selected_model: str,
) -> list[dict[str, float | date]]:
    history = list(values)
    predictions: list[dict[str, float | date]] = []
    for _offset in range(horizon):
        target_day = first_day + timedelta(days=len(history))
        if selected_model == "random_forest_lag_features":
            if bundle.estimator is None:
                raise ValueError("The selected random forest artifact is unavailable")
            point = max(
                0.0,
                float(bundle.estimator.predict([make_features(history, target_day)])[0]),
            )
        elif selected_model == "seasonal_naive_7_day":
            point = history[-7]
        else:
            point = history[-1]
        low = min(point, max(0.0, point + bundle.residual_low))
        high = max(point, point + bundle.residual_high)
        predictions.append({"day": target_day, "point": point, "low": low, "high": high})
        history.append(point)
    return predictions


def top_factors(bundle: DemandBundle, count: int = 5) -> list[dict[str, float | str]]:
    ranked = sorted(bundle.feature_importance.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return [{"feature": "recent_seasonal_demand", "importance": 1.0}]
    return [{"feature": name, "importance": value} for name, value in ranked[:count]]
