# ML Architecture

## Purpose and constraints

ML supports decision-making; it does not silently alter financial records or inventory. Every prediction should identify its business, target entity, target period, model/version, generated time, input cutoff, and uncertainty where available. Keep a baseline available as a fallback and make recommendations explainable enough for a business operator to review.

## Pipeline

```text
Historical transactions + inventory + calendar/context
        ↓ validated, tenant-scoped snapshots
Feature engineering (as-of-time; no future leakage)
        ↓
Baselines (naive, seasonal naive, moving average / ETS)
        ↓ rolling-origin evaluation and model selection
Demand forecasts (point + quantiles/intervals where calibrated)
        ├── Stock-out risk predictions
        ├── Anomaly detection and review queue
        └── Inventory optimization / reorder recommendations
                 ↓ persisted results + provenance
Application API and user review
```

## Phase 6 implementation

The backend now contains a product-level daily-demand trainer/evaluator (`python -m
app.ml.train_demand`) and stored-forecast inference routes. Candidate models are a last-observation
naive, a 7-day seasonal-naive baseline, and a random forest using lag/rolling/calendar features.
Training is an offline command so a long fit does not block an API request. Insufficient history
returns a data-readiness result and does not create predictions. The measured synthetic fixture
and its limits are documented in `ML_EVALUATION_REPORT.md`.

Stock-out risk aggregates future product forecasts, recipe-derived ingredient demand, current
stock, supplier lead time, and forecast intervals. Its current normal approximation is
uncalibrated and exposes that assumption in the saved prediction. Isolation Forest runs on
available sales, refunds, per-item inventory movements, and per-supplier-item price histories;
groups with fewer than 20 rows are skipped. No anomaly accuracy is reported without labels.

Forecasting and stock-out outputs are served through FastAPI and stored with model version,
timestamp, important factors, and uncertainty/provenance. Model versions and metrics are recorded
in `model_versions`; trusted serialized artifacts live in `ML_ARTIFACT_DIR`. A graph neural network
is deferred because this repository has no populated relational history or suitable labels to
justify its added complexity.

## Data and feature engineering

Start with daily or weekly product/location sales, returns/refunds, stock availability, stock movements, promotions/prices if captured, holidays, and lead times. Store event time and ingestion/recorded time separately where late corrections matter. Build features using only information available at the forecast cutoff. Track missing periods and stockout censoring: sales during a stockout understate unconstrained demand. Include product lifecycle and changing catalog mappings explicitly.

Use a reproducible training dataset snapshot or query cutoff, feature code version, model parameters, and evaluation window. Validate tenant isolation and data quality before training. Avoid training on synthetic demo data as evidence of operational performance.

## Model progression and evaluation

1. Validate a transparent baseline: last value, seasonal naive, and/or moving average/ETS as data permits.
2. Compare candidates using rolling-origin time-series splits, not random row splits. Report error by horizon and segment (for example MAE/RMSE plus scaled or percentage measures where their denominators are safe).
3. Evaluate quantile/interval coverage and width before using uncertainty in safety stock.
4. Evaluate stockout models with temporal validation and operational precision/recall at useful alert thresholds; assess class imbalance.
5. Compare anomaly detection to rules and reviewed historical cases; anomalies are flags for investigation, not proof of fraud/error.
6. Optimize inventory against explicit service-level, lead-time, MOQ, expiry, and cost assumptions; show assumptions with each recommendation.

Model choice should follow evidence: scikit-learn and statsmodels are sufficient for early tabular/baseline work; evaluate XGBoost for nonlinear features. PyTorch and advanced forecasting libraries are research options, not prerequisites.

## Serving and application connection

Training runs as an offline command or worker. A model artifact and metadata are versioned in an artifact store (initially a controlled filesystem/object store) with a database record describing target, version, training cutoff, metrics, and status. Inference can be a Python module called by an application worker initially; isolate it behind an inference interface so it can later become a separate service.

On a schedule or after qualifying events, a job loads an approved model, generates outputs, writes Forecast/Prediction/Anomaly/Recommendation rows with provenance, and emits corresponding events via the outbox. FastAPI serves stored results and accepts user feedback/overrides. Do not train a model in an HTTP request. Keep deterministic rules for critical stock thresholds when ML is unavailable.

## Monitoring and governance

Track data freshness, missingness, feature distributions, forecast error as actuals arrive, interval coverage, model version, inference failures/latency, and override/acceptance rates. Define retraining triggers based on drift/performance and minimum data, not arbitrary frequent retraining. Keep a rollback path to the prior model and baseline. Access to training datasets and artifacts follows business-level data permissions; apply retention and deletion policy to derived datasets too.

## Research extension

Probabilistic forecasts can represent demand uncertainty and improve safety-stock decisions if calibrated and evaluated against service/cost outcomes. Graph-based relationships (substitutes, bundles/recipes, supplier/product links, locations) may improve cold-start or propagation analysis; represent these links relationally first, then test graph features or graph models against baselines. Real-time streams can reduce data latency, but are warranted only if decisions need sub-batch freshness. A useful research study compares each addition independently with temporal backtests and operational metrics.
# Event-driven ML intake (Phase 7)

The `ml` Redpanda consumer group records deduplicated `SALE_CREATED`, `INVENTORY_UPDATED`, and `FORECAST_UPDATED` events as `ml_event_tasks`. A background task processor resolves affected products, coalesces events in batches, and invokes the existing temporal evaluation/training service using real business sales. A selected product model is reused for 15 minutes to avoid fitting on every sale. Insufficient sales history is recorded as such; the task is not represented as a successful prediction. The event and task IDs remain available for replay and audit.
