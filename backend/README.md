# Morrow API foundation

FastAPI + SQLAlchemy 2 async API with PostgreSQL, Alembic, tenant-aware repositories, service-layer rules, bearer JWT authentication, Argon2 password hashes, RBAC, request validation, structured logs, audit records, and a transactional outbox for inventory changes and new orders.

## Local development

At the repository root, run `docker compose up --build`. This starts a development-only PostgreSQL database, Redpanda, the API, and the event worker. The API applies all pending Alembic revisions before serving at `http://localhost:8000`. Interactive API docs are at `/docs`, liveness is `/health`, and database readiness is `/health/ready`. Local database credentials and the compose signing key are for development only.

To run without Docker, install Python 3.11+ and from `backend/` run `python -m venv .venv`, activate it, `pip install -e '.[dev]'`, copy `.env.example` to `.env`, set a unique `SECRET_KEY`, and run `alembic upgrade head` followed by `uvicorn app.main:app --reload`. The configured database must be PostgreSQL for normal operation.

Supplier invoice OCR also requires the system Tesseract executable. The provided backend Docker image installs it. For a local host install, install Tesseract OCR for your operating system before using `POST /api/v1/invoices/ocr-captures`; OCR drafts remain uncommitted as invoices until a user confirms the verified details.

## API paths

The API is versioned under `/api/v1`. Inventory operations include product and ingredient stock, unit conversion, recipe management, threshold alerts, movement history, wastage, stock adjustment, batches, and supplier catalogs with price history. Purchase orders do not change stock until goods are received through `POST /api/v1/purchases/{id}/goods-received`; receipts create batches, movements, accounting entries, audit records, and outbox events transactionally. Sales consume recipe ingredients when a recipe exists, or sellable product stock otherwise. ML routes serve stored forecasts, generate stock-out predictions, and detect anomalies. Demand model training runs offline with `python -m app.ml.train_demand`; rule based stock alerts remain separate from ML predictions.

Demand forecast APIs are `GET /api/v1/forecasting`, `POST /api/v1/forecasting/generate`,
`POST /api/v1/forecasting/stockout-predictions`, and `GET /api/v1/forecasting/models`.
Anomalies use `POST /api/v1/anomalies/detect` and `GET /api/v1/anomalies`. To reproduce the
explicitly synthetic evaluation fixtures, run `python -m app.ml.synthetic_evaluation` from
`backend/`. Results and limitations are recorded in the root `ML_EVALUATION_REPORT.md`.

## Real-time events

Business services write event rows to PostgreSQL's transactional outbox as part of the same transaction as each operation. The `event-worker` publishes those rows to Redpanda and maintains independent consumer groups for realtime storage, analytics, ML intake, notifications, audit, and rule-based reorder suggestions. Delivery is at least once; stable event IDs and per-consumer receipts protect side effects from duplicates. Exhausted events go to `business.events.dlq.v1` for inspection and replay.

The v1 envelope is documented in `app/events/schemas/business-event-v1.schema.json`. `GET /api/v1/events/stream` is authenticated and streams persisted events for the current business; clients reconnect with the last SSE cursor. `GET /api/v1/analytics/realtime`, `GET /api/v1/notifications`, and `GET /api/v1/recommendations` expose the consumer projections. The ML consumer queues event work and a background processor coalesces product updates, then runs measured training from real sales history at most once per product per 15 minutes; tasks with insufficient history remain explicitly labeled.

## Automatic stock phone alerts

The `voice_calls` Redpanda consumer queues one outbound spoken call when stock crosses into low, critical, or out-of-stock. The independent event worker submits the call and polls its provider status, so the browser does not need to be open. Delivery tasks are deduplicated by source event and retry a bounded number of times. Only an owner can configure the destination using `GET/PUT /api/v1/voice/stock-alerts`; the destination must be E.164 format (for example, `+14155550123`). Recent call delivery records are available from `GET /api/v1/voice/stock-alerts/calls`.

To enable actual calls, set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` in the project root `.env`, then restart/rebuild the Compose services. Use a Twilio Voice-enabled number or verified outgoing caller ID. With trial accounts, the destination may also need to be verified. Then sign in as the business owner and enable alerts through the API. The call says the stock item, alert level, and current quantity twice. No payment/order action is performed. Without provider credentials, alert settings cannot be enabled and no call is represented as sent. The local app does not require a public callback URL because the TwiML is sent with the outbound call request; call status is polled by the worker.

## Provision voice conversations

Provision contacts are tenant-scoped records managed only by the owner at `/api/v1/voice/contacts`.
Indian operational numbers must use `+91` E.164 format. Record consent before activation; no contact is seeded into a database migration because migrations cannot safely infer the correct tenant.

`VOICE_TEST_MODE=true` is the default and cannot dial a telephone number. It supports the complete mocked owner authorization flow:

1. Configure an active owner contact with calling consent.
2. Ensure an inventory item is at a rule-based low, critical, or out-of-stock level.
3. `POST /api/v1/voice/conversations/owner-shortage` creates a durable shortage snapshot and opening turn.
4. `POST /api/v1/voice/conversations/{id}/mock-response` accepts a transcript or DTMF `1`, `2`, or `3`.

Only an explicit owner approval authorizes supplier contact for quotations. It never authorizes a purchase. The result, turns, decision, and audit entries are persisted.

Live owner calls require all of the following: valid Twilio credentials, `VOICE_TEST_MODE=false`, `VOICE_LIVE_CALLS_ENABLED=true`, and a public HTTPS `VOICE_PUBLIC_BASE_URL`. The service validates Twilio webhook signatures and accepts speech/DTMF through signed `<Gather>` callbacks. A ConversationRelay WebSocket endpoint is included as an opt-in integration boundary, but it requires an externally reachable `wss://` deployment and Twilio account/feature validation before it can be enabled. Do not turn on live calling until every contact has consented and authorized test calls have been completed.

Registration creates one business and grants the initial user the owner role; any client-supplied role is ignored. Subsequent calls require an `Authorization: Bearer <token>` header. The token is scoped to its initial business. Membership and role checks run on protected routes, and repositories constrain tenant-owned records by `business_id`.

## Configuration

See `.env.example`. Production requires a unique 32+ character signing secret and explicit non-wildcard CORS origins. Password reset uses a non-enumerating acknowledgement until an email provider is configured. Rate limiting is currently process-local and suitable only as a development safety layer; use a shared gateway/Redis limiter for multiple API workers. Never use the compose secret or database password in deployment.

## Tests

Run `pytest` from `backend/`. Tests use an isolated in-memory SQLite database for API/service behavior; production/local application configuration targets PostgreSQL. Install dev requirements with `pip install -e '.[dev]'` first.

## Inventory workflow and boundaries

Inventory quantities are stored in the product or ingredient's base unit. Recipes convert configured quantities into the ingredient base unit at save time. Purchase quantities use that same base unit. Goods receipts can include lot codes and expiration dates; stock is consumed FEFO (earliest expiry first), with expired batches excluded from sales. Inventory valuation uses weighted average unit cost while batches retain their receipt cost. Unbatched opening balances remain supported.

Low, critical, out-of-stock, expiring, and overstock conditions are derived from configured thresholds and dates. Alert responses carry `source: rule_based` and `ml_prediction: null`. They must not be presented as model output. Tax policy is not defined, so order tax is recorded as zero. Payment/refund providers and email delivery remain outside this phase; this is not a complete payment or accounting system. See `ML_EVALUATION_REPORT.md` for model scope and measured synthetic-fixture results.
