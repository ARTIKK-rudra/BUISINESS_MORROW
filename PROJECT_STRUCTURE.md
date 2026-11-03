# Project Structure

Proposed monorepo layout. This describes a future structure; no application code is created in Phase 0.

```text
.
├── ARCHITECTURE.md
├── TECHNOLOGY_DECISIONS.md
├── PROJECT_STRUCTURE.md
├── ML_ARCHITECTURE.md
├── DATABASE_SCHEMA.md
├── README.md
├── .env.example
├── .gitignore
├── compose.yaml
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/                 # routes and layouts
│   │   ├── components/          # reusable UI
│   │   ├── features/            # inventory, sales, forecasts, etc.
│   │   ├── lib/                 # API client, auth, formatting
│   │   └── types/
│   └── public/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── app/
│   │   ├── main.py              # FastAPI composition
│   │   ├── api/v1/              # HTTP routes and request schemas
│   │   ├── core/                # config, auth, logging
│   │   ├── domains/
│   │   │   ├── identity/
│   │   │   ├── catalog/
│   │   │   ├── inventory/
│   │   │   ├── procurement/
│   │   │   ├── sales/
│   │   │   ├── finance/
│   │   │   ├── intelligence/
│   │   │   └── engagement/
│   │   ├── integrations/        # OCR, payments, messaging, voice
│   │   ├── events/              # event contracts, outbox, publisher
│   │   ├── jobs/                # scheduled and asynchronous tasks
│   │   └── db/                  # engine, session, shared persistence
│   └── ml/
│       ├── datasets/
│       ├── features/
│       ├── models/
│       ├── evaluation/
│       ├── inference/
│       └── registry/            # metadata/artifact references
├── docs/
│   ├── api/
│   └── decisions/               # accepted ADRs
└── deploy/
    ├── docker/
    └── environments/
```

## Dependency direction

HTTP routes and workers depend on domain services. Domain services own business decisions and depend on interfaces for persistence and external integrations. Database and provider adapters implement those interfaces. ML training code may depend on curated data/feature interfaces, but business modules should not import notebook code. Shared event contracts should be versioned and contain identifiers and facts needed by consumers, not ORM objects or sensitive payloads.

## Naming and boundaries

Organize by business capability rather than a large global `models/` or `utils/` directory. Keep API schemas separate from persistence models. Treat notebooks as exploratory and move repeatable work into importable modules with recorded parameters and evaluation outputs. Do not introduce separate repositories or deployables until ownership or scaling requires them.
# Phase 7 event modules

- `backend/app/events/contracts.py` defines the versioned business event envelope and supported event names.
- `backend/app/events/schemas/business-event-v1.schema.json` is the JSON Schema contract published with the application.
- `backend/app/events/worker.py` runs the PostgreSQL outbox publisher plus separate consumer groups and their retry/DLQ behavior.
- `backend/app/api/v1/endpoints/events.py` provides authenticated, replayable SSE delivery from the persisted realtime projection.
- `frontend/src/lib/api.ts` reads the authenticated stream; the application shell displays the latest live business event and reconnect status.
- `backend/migrations/versions/0006_realtime_events.py` adds delivery state, idempotency receipts, realtime projections, ML intake, and notification source IDs.
