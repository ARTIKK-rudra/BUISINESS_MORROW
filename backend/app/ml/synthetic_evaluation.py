"""Reproducible labeled synthetic fixture for pipeline smoke evaluation only."""

from datetime import date, timedelta

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from app.ml.demand import evaluate_and_fit
from app.services.forecasting import stockout_probability


def evaluate_synthetic_fixture() -> dict:
    rng = np.random.default_rng(20260928)
    start = date(2025, 1, 1)
    values = []
    for index in range(365):
        day = start + timedelta(days=index)
        weekday_effect = [1.5, 0.8, 0.5, 0.5, 1.0, 4.0, 5.0][day.weekday()]
        annual_effect = 1.3 * np.sin(2 * np.pi * index / 365)
        expected = max(0.2, 16 + 0.015 * index + weekday_effect + annual_effect)
        values.append(float(rng.poisson(expected)))
    result = evaluate_and_fit(values, start)
    return {
        "dataset_kind": "synthetic_fixture",
        "dataset_label": (
            "Generated Poisson demand with trend, weekday seasonality, and annual seasonality"
        ),
        "seed": 20260928,
        "observations": len(values),
        "supervised_rows": result["supervised_rows"],
        "holdout_start": result.get("holdout_start"),
        "holdout_end": result.get("holdout_end"),
        "evaluations": result["evaluations"],
        "selected_model": result.get("selected_model"),
        "warning": (
            "Synthetic smoke result only; it is not evidence of performance on a real business."
        ),
    }


def evaluate_synthetic_anomalies() -> dict:
    rng = np.random.default_rng(20260929)
    training = np.column_stack(
        (
            rng.normal(3.0, 0.45, 1000),
            rng.beta(1.2, 12.0, 1000),
            rng.integers(1, 6, 1000),
        )
    )
    ordinary = np.column_stack(
        (
            rng.normal(3.0, 0.45, 500),
            rng.beta(1.2, 12.0, 500),
            rng.integers(1, 6, 500),
        )
    )
    injected = np.column_stack(
        (
            rng.normal(7.0, 0.2, 50),
            rng.uniform(0.45, 0.9, 50),
            rng.integers(15, 40, 50),
        )
    )
    features = np.vstack((ordinary, injected))
    labels = np.array([0] * len(ordinary) + [1] * len(injected))
    scaler = RobustScaler(quantile_range=(10, 90)).fit(training)
    detector = IsolationForest(n_estimators=250, contamination="auto", random_state=42, n_jobs=1)
    detector.fit(scaler.transform(training))
    predicted = detector.predict(scaler.transform(features)) == -1
    true_positive = int(np.sum(predicted & (labels == 1)))
    false_positive = int(np.sum(predicted & (labels == 0)))
    false_negative = int(np.sum(~predicted & (labels == 1)))
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
    )
    return {
        "dataset_kind": "synthetic_fixture",
        "dataset_label": "Known injected high-value, high-discount, high-item-count outliers",
        "training_rows": len(training),
        "test_rows": len(features),
        "injected_anomalies": len(injected),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "warning": "Synthetic injected-outlier benchmark; not operational anomaly accuracy.",
    }


def evaluate_synthetic_stockout_risk() -> dict:
    rng = np.random.default_rng(20260930)
    probabilities = []
    outcomes = []
    for _ in range(1000):
        lead_days = int(rng.integers(3, 15))
        mean_daily_demand = float(rng.uniform(1.0, 12.0))
        on_hand = float(rng.uniform(lead_days * 0.5, lead_days * mean_daily_demand * 1.5))
        expected = lead_days * mean_daily_demand
        standard_deviation = float(np.sqrt(lead_days * mean_daily_demand))
        probability = stockout_probability(on_hand, expected, standard_deviation)
        realized = float(rng.poisson(mean_daily_demand, size=lead_days).sum())
        probabilities.append(probability)
        outcomes.append(float(realized >= on_hand))
    base_rate = float(np.mean(outcomes))
    outcomes_array = np.asarray(outcomes)
    brier = float(np.mean((np.asarray(probabilities) - outcomes) ** 2))
    baseline_brier = float(np.mean((base_rate - outcomes_array) ** 2))
    return {
        "dataset_kind": "synthetic_fixture",
        "dataset_label": "Independent Poisson daily demand with known mean and supplier lead time",
        "scenarios": len(outcomes),
        "observed_stockout_rate": base_rate,
        "brier_score": brier,
        "constant_base_rate_brier": baseline_brier,
        "brier_skill_vs_constant_rate": (1 - brier / baseline_brier if baseline_brier else 0.0),
        "warning": (
            "Synthetic distributional smoke test only; real forecast errors, dependence, "
            "expiry, and supplier uncertainty are not represented."
        ),
    }


if __name__ == "__main__":
    import json

    print(
        json.dumps(
            {
                "demand_forecasting": evaluate_synthetic_fixture(),
                "anomaly_detection": evaluate_synthetic_anomalies(),
                "stockout_risk": evaluate_synthetic_stockout_risk(),
            },
            indent=2,
            sort_keys=True,
        )
    )
