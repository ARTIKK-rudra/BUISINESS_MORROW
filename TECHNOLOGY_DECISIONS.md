# Technology Decisions

Status: current prototype uses React/Next.js, FastAPI, PostgreSQL, SQLAlchemy/Alembic, and scikit-learn. Revisit choices as measured data and operational needs change.

| Area | Proposed choice | Reason and boundary |
|---|---|---|
| Web UI | Next.js + React + TypeScript | Good fit for a typed dashboard and routing. Prefer server-rendered pages only where useful; the app can remain a client-heavy authenticated dashboard. A plain Vite React app is a simpler alternative if there is no public/SEO-facing surface. |
| API/business logic | Python + FastAPI + Pydantic | One typed HTTP boundary and convenient sharing of Python data/ML tooling. Keep business rules in domain services, not route handlers. |
| Primary database | PostgreSQL | Transactions, relational constraints, reporting queries, JSONB where appropriate, and mature deployment options. Keep core business facts normalized; do not make JSONB the schema. |
| Persistence/migrations | SQLAlchemy 2 + Alembic (proposed) | Mature Python ORM and explicit schema migrations. Review whether a lighter SQL approach better suits the team's experience before coding. |
| ML | Python, pandas/Polars as measured, scikit-learn, statsmodels where useful | Establish naive and seasonal baselines first. Add XGBoost only when feature-based benchmarks improve. PyTorch is justified only for a demonstrated deep-learning research question and adequate data. |
| Forecasting | Baseline seasonal-naive/ETS, then evaluate statsmodels or a maintained forecasting library against rolling-origin validation | Forecasting library choice depends on number of series, covariates, intermittent demand, hierarchy, and data volume. Probabilistic intervals are useful for inventory decisions but require calibration. |
| Events | PostgreSQL transactional outbox initially; broker later (Redpanda or Kafka) | A broker is not needed to demonstrate event-driven boundaries at low volume. If asynchronous consumers/replay become material, choose one broker; Redpanda can reduce operational overhead for Kafka-compatible workloads, while Kafka has a broad ecosystem. |
| Cache | None initially; Redis only for measured hot reads, rate limits, or coordination | Avoid cache invalidation and another stateful dependency before evidence of need. PostgreSQL is not a general-purpose job queue. |
| OCR | Provider/library behind an OCR adapter; evaluate local OCR versus managed service on actual invoices | Accuracy, language/layout coverage, privacy, and cost decide. Keep extraction results reviewable; OCR is not authoritative accounting data. |
| Voice | Defer; adapter-based speech-to-text/text-to-speech integration if a concrete workflow exists | Voice adds consent, privacy, latency, and provider concerns without being core to inventory forecasting. |
| Notifications | Persist notification intent and delivery state; send through provider adapters asynchronously | Enables retry and in-app history. Select email/SMS/push provider after channel and geography are known. |
| Packaging | Docker and Compose for reproducible local development; production orchestrator selected later | Containers improve portability; Kubernetes is not a default requirement for a small prototype. |
| Object files | S3-compatible object storage if invoice/audio uploads are required | Keep binary documents outside relational rows, with access controls and retention policies. |

## Phase 8 implementation choices

- Supplier invoice extraction uses local Tesseract OCR via `pytesseract` and Pillow. The API retains extracted text and editable structured draft data, not the uploaded image. The Docker image installs the Tesseract engine; local non-Docker deployments must install it separately.
- The first business assistant uses verified query templates over tenant-scoped application data. It does not use an LLM because a general language model would add hallucination risk without a configured retrieval and evaluation layer.
- Voice input uses browser Web Speech APIs, with microphone permission requested only after a click. Browser support varies; typed input remains available. Transcript persistence is opt-in.

## Use later only with evidence

- **Redpanda/Kafka:** asynchronous fan-out, replay, or sustained throughput that an outbox poller cannot meet.
- **Redis:** measured cache hit opportunity, rate limiting, or distributed coordination.
- **PyTorch/deep networks:** sufficient history and an explicit experiment where simpler models underperform.
- **Graph database:** only if graph queries are a first-class workload that relational joins cannot support adequately. Product/business relationships can initially be modeled relationally.
- **Kubernetes/microservices:** independent scaling/ownership/deployment needs that justify operational complexity.
- **Vector database/LLM:** no current core requirement. Do not add for ordinary forecasting, inventory arithmetic, or reporting.

## Avoid for this project at the start

Avoid simultaneous adoption of Kafka and Redpanda; Redis as a default; separate microservices for every listed capability; a graph database before graph-shaped query evidence; PyTorch solely because it is popular; a second primary database; and an LLM as the source of numerical forecasts or financial truth. These increase operational and validation burden without a demonstrated benefit.

## Phase 6 implementation note

Scikit-learn is now a runtime dependency for a per-product random forest candidate and Isolation Forest anomaly review signals. Naive and seasonal-naive demand models are evaluated as baselines. Demand training runs as an offline command; forecasts and model metadata are served through FastAPI. No graph model is included because the repository has no populated, labeled relational history. See `ML_EVALUATION_REPORT.md` for the synthetic fixture measurements and their limits.
# Phase 7: Redpanda event transport

**Decision:** Add Redpanda behind the existing PostgreSQL transactional outbox. The project now has real use cases for independent delivery to realtime dashboards, analytics projections, ML task intake, audit, notifications, and rule-based recommendations. The broker is used for consumer offsets, fan-out, replay, and failure isolation; it is not a replacement for transactional domain storage.

**Client:** `aiokafka` uses the Kafka protocol supported by Redpanda. The publisher enables idempotent broker retries and `acks=all` through the client setting. Application-level delivery remains at least once because PostgreSQL and Kafka cannot share one atomic transaction; stable event IDs and consumer receipts make effects duplicate-safe.

**Local topology:** One Redpanda node and explicit `business.events.v1` / `business.events.dlq.v1` topics in Compose. This is for development and demonstrations, not production durability. The API does not require Redpanda to complete a sale; it writes the outbox row transactionally and the worker publishes asynchronously.

**Alternatives deferred:** Direct broker writes from request handlers create a database/broker dual-write failure window. PostgreSQL polling alone would not provide independent consumer offsets or replay. Kafka-compatible managed services can replace Redpanda without changing the event contract.
