# Architecture

## Phase 0 status

Repository reconnaissance on 2026-09-27 found an empty workspace: no source files, dependency manifests, framework configuration, database setup, tests, or deployment assets. Git history/status could not be inspected because the machine has no active Xcode Command Line Tools installation. There is therefore no existing implementation to continue or refactor. Recommendation: start clean, retaining this repository, and introduce components incrementally after requirements and data access are confirmed.

## System shape

```text
Browser (Next.js / TypeScript)
        │ HTTPS / JSON
        ▼
FastAPI application ── domain services ── PostgreSQL
        │                      │                  │
        │                      ├── ML inference   ├── transactional records
        │                      ├── OCR adapter    └── outbox records
        │                      └── notifications
        │
        └── outbox publisher ── event broker (defer until justified)
                                  ├── analytics / forecast workers
                                  └── notification workers
```

Start as a modular monolith: one deployable FastAPI application, clear domain modules, PostgreSQL as the system of record, and separately runnable worker processes only when their workload needs it. This keeps the academic prototype understandable and deployable while preserving boundaries for later extraction. Avoid making every diagram box a network service at the outset.

## Request and data flow

1. The browser calls versioned API endpoints over HTTPS. Authentication establishes a user and business scope; authorization checks both role and resource ownership.
2. The API validates input, invokes a domain service, and commits related writes in one PostgreSQL transaction. Financial and inventory changes are recorded as append-only movements/ledger entries; current balances are derived or maintained transactionally with reconciliation.
3. The same transaction writes an outbox event. A publisher later forwards committed events to consumers. This avoids a database/broker dual-write gap.
4. Workers build features, run forecasts or anomaly checks, persist model/run metadata and results, and emit result events. API reads expose persisted results; synchronous inference is reserved for low-latency use cases that need it.
5. External services (OCR, email/SMS, speech recognition) sit behind adapters with timeouts, retries, idempotency, and explicit provider configuration.
6. Supplier invoice OCR runs locally through Tesseract. It stores extracted text and editable fields as a review draft; only an authenticated confirmation creates an invoice and its verified lines. Invoice confirmation does not post a purchase, payment, or inventory movement.
7. The business assistant uses a closed set of tenant-scoped database queries. It does not send business questions to an unconfigured external language model, and it reports missing stored forecasts or anomaly results instead of inventing values. Its reorder answers are read-only recommendations.
8. Voice input and spoken output use the browser Web Speech APIs after an explicit microphone action. Transcript storage is opt-in; unsupported browsers keep the typed assistant available.
9. Low-stock reorder recommendations are explicitly labeled rule-based. Their purchase approval endpoint is restricted to the business owner, rechecks inventory and supplier price, records the approval and creates the purchase order in one database transaction. Normal manual procurement keeps its existing permissions.

## Domain boundaries

- **Identity and tenancy:** Business, User, Role, AuditLog.
- **Catalog:** Product, Category, Ingredient, Recipe.
- **Inventory and procurement:** Inventory, InventoryMovement, Supplier, SupplierProduct, Purchase, PurchaseItem.
- **Sales and finance:** Customer, Order, OrderItem, Payment, Refund, Expense, LedgerEntry, Invoice.
- **Intelligence:** Forecast, Prediction, Anomaly, Recommendation.
- **Engagement:** Notification, VoiceInteraction.

Business is the tenant root. Tenant-owned rows carry `business_id` (directly or through a parent) and queries must enforce that scope. Use role assignments scoped to a business rather than assuming a global role name grants access everywhere. Define money as fixed precision plus ISO currency; never use binary float for stored monetary amounts.

## Non-functional design

- **Consistency:** PostgreSQL transactions for order, payment state, inventory movements, and outbox inserts. Idempotency keys for retried commands/webhooks.
- **Security:** TLS at ingress; hashed credentials or an OIDC provider; least-privilege roles; secret manager/environment injection; audit sensitive actions; validate uploads and provider callbacks.
- **Reliability:** Health/readiness endpoints, structured logs, request/event correlation IDs, bounded retries, dead-letter handling once a broker exists, and database backup/restore procedures.
- **Observability:** Start with structured application logs and basic metrics. Add tracing when multiple deployables or external integrations make request paths hard to diagnose.
- **Privacy:** Minimize customer/voice data, define retention and deletion rules, and keep raw audio/OCR documents out of ordinary logs.

## Deployment evolution

Local development can use Docker Compose for the API, PostgreSQL, and optionally a web frontend. Production can deploy the same API and worker images behind a managed ingress, with managed PostgreSQL and managed object storage for documents. Add Redis only for measured cache/queue/coordination needs, and a broker only when independent asynchronous consumers, throughput, or replay requirements justify its operational cost. Keep configuration external and migrations versioned. The design allows API, ML workers, and event consumers to scale independently later without requiring that split in the first release.

## Open decisions before implementation

Confirm initial business domain and workflows, tenancy/isolation expectations, supported currency/time zones, tax/accounting scope, payment provider, deployment target, data availability and granularity, forecast horizon, OCR/voice providers, and retention/privacy constraints. These affect schema constraints and integration boundaries and should not be guessed in code.
# Real-time event delivery (Phase 7)

Business writes remain transactional in PostgreSQL. Each sale, refund, purchase, inventory change, forecast, and anomaly stores its domain rows and an `outbox_events` row in the same database transaction. The `event-worker` claims unpublished outbox rows with row locks, publishes the versioned envelope to Redpanda, and marks the row published only after broker acknowledgement. It keys messages by business and aggregate so updates for one aggregate stay partitioned together; a sale and its inventory events carry the order reference and are committed atomically with the stock mutation. A crash between broker acknowledgement and the database update can publish a duplicate; every consumer therefore records `(event_id, consumer_name)` in `event_consumer_receipts` in the same transaction as its effects.

The worker runs separate Kafka consumer groups for `database`, `analytics`, `ml`, `notifications`, `audit`, and `recommendations`. Each group can retry independently. Repeated failures are copied to `business.events.dlq.v1`; malformed records are dead-lettered before their offset is advanced. The producer also keeps failed outbox rows in PostgreSQL with exponential retry timing and sends exhausted rows to the DLQ. DLQ publication failures do not discard the original outbox row or consumer offset.

The `database` consumer writes durable tenant-scoped rows to `realtime_events`. The authenticated `GET /api/v1/events/stream` endpoint polls this projection and emits replayable SSE frames. The frontend reads that stream with the in-memory bearer token, reconnects from the last sequence cursor, and refreshes the dashboard's event-derived totals without a page reload. Analytics groups monetary totals by currency so unrelated currencies are not added together. ML records deduplicated feature refresh tasks, then a background task processor coalesces work and calls the measured model training service from real sales history. Notification, audit, and rule-based reorder consumers each have their own idempotency boundary. Model work stays outside the sale request transaction.

Redpanda is used here because this phase now needs independent fan-out, consumer offsets, replay, and failure isolation for live analytics. A single-node broker is provided for local development; deployment should use a multi-node cluster, replication factor appropriate to the environment, managed credentials/TLS, topic retention policies, monitoring, and independent worker replicas. PostgreSQL remains the source of truth; Redpanda is the durable event transport and replay log.
