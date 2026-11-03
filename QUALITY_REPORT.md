# Phase 10 — Security, Testing & Quality Report

**Review date:** 2026-09-29  
**Scope:** Backend security and behavior, frontend integration and route review, ML evaluation, and local performance profiles.

## Changes made

- Removed fixed Compose signing and database passwords. Compose now requires `SECRET_KEY` and `POSTGRES_PASSWORD`; root `.env.example` and `.gitignore` establish local secret handling.
- Production settings reject development/example secrets, non-PostgreSQL database URLs, wildcard/non-HTTPS CORS, and HTTPS URLs that are not valid origins.
- Added `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy` response headers.
- Bounded the process-local rate-limit key map and grouped limits by client and endpoint class, rather than attacker-controlled URL IDs. Authentication and expensive voice/OCR paths have separate limits.
- OCR continues to require user confirmation before creating a purchase. Uploads are size- and format-checked, and OCR execution has a timeout.
- Supplier intelligence now batches related reads. Its measured profile went from 30 to 7 SQL statements for 4 suppliers and 8 offers.
- Added explicit HTTP API adapters for product, inventory, and sale response models. Inventory summary metrics are derived from loaded records; category/status controls filter those records.
- Removed unsupported Terms/Privacy copy and a hard-coded sample business identity from the POS receipt. Existing preview and unavailable states remain labeled.
- Added Playwright route, mobile-navigation, command-palette, preview-POS, password-reset, and authentication-preview scenarios.

## Verification performed

- `backend/.venv/bin/pytest -q`: **30 passed**. Covers transaction and rollback behavior, concurrency, tenant isolation, role authorization, JWT tampering/expiry/type, request validation, rate limiting, OCR upload checks, event idempotency, ML holdout/reproducibility/edge cases, and supplier/API profiles.
- `backend/.venv/bin/ruff check app tests`: passed.
- `backend/.venv/bin/ruff format --check app tests`: passed (95 files).
- Local SQLite/ASGI smoke profile, not production measurements:
  - `GET /products`, 20 requests: p50 **2.11 ms**, p95 **5.43 ms**.
  - Notification event processing: **2.69 ms**.
  - Supplier intelligence: **4.66 ms**, **7 SQL statements** for 4 suppliers/8 offers.
- The tracked `ML_EVALUATION_REPORT.md` labels the demand and anomaly results as synthetic fixtures and labels stock-out probabilities as uncalibrated. No real business accuracy claim is made.
- Scanned project text for obvious committed credentials/private keys; Compose no longer contains fixed credentials. The development-only default signing key is explicitly rejected by production settings.

## Security review summary

| Area | Reviewed behavior | Remaining concern |
|---|---|---|
| Authentication | Argon2 password hashing, signed expiring access JWTs, validation for token signature/expiry/type; unauthenticated protected routes rejected | Tokens are browser-memory bearer tokens; no refresh/revocation flow, MFA, or email verification. Production should use an httpOnly session/BFF and complete account lifecycle controls. |
| Authorization and tenant isolation | Role permission dependencies and business-scoped repository queries; tests reject cross-business inventory access and inactive business membership | Continue extending cross-tenant tests to every object-ID endpoint as domains are added. |
| API/input security | Pydantic request constraints, normalized API errors, request IDs, role gates and rate limiting | The current limiter is process-local. Put distributed throttling at a trusted API gateway or Redis before multi-worker deployment. Do not trust client-supplied forwarding headers without a configured proxy boundary. |
| Secrets/configuration | Compose requires externally supplied values; production rejects unsafe defaults | Keep `.env` out of version control and provision unique secrets in deployment secret storage. Compose password interpolation expects URL-safe characters; generate hex passwords or URL-encode them. |
| Database | SQLAlchemy parameterized ORM access, business filters, foreign keys/constraints and transactional services | Verification used SQLite test DB. PostgreSQL locking, migration, isolation and query plans were not run in this environment. |
| Upload/OCR | Bounded reads, allowed image format/content check, OCR timeout, authenticated endpoint and manual confirmation before persistence | Container OCR binary and adversarial file fuzzing were unavailable. Add malware scanning and private object storage if uploads leave process memory. |
| Voice/assistant | Protected routes, consent before transcript storage, business-data grounded answers | No independent speech provider or production voice privacy review was available. Browser speech output requires explicit user opt-in in UI. |
| Audit | Business operations create audit records; API request logging includes request ID/status/latency | Review retention, access controls, and sensitive-data redaction before production log export. |

## Test coverage added

The backend suite now includes unit/service, API, tenant/authorization, OCR, event consumer, ML evaluation and edge-case, transaction, concurrency, rollback, and performance smoke tests. Frontend Playwright scenarios are in `frontend/e2e/quality.spec.ts`; they are authored but have not been executed.

## Not verified in this environment

The workstation has no `node`, `npm`, `docker`, `psql`, or `tesseract` executable. Consequently the Next.js typecheck/build and Playwright browsers, Compose startup, PostgreSQL integration/migrations, Redpanda broker delivery/retries/DLQ, Tesseract OCR execution, and production browser console/performance checks could not be run. No claim of “zero console errors” or production performance is made.

Before deployment, run the frontend install/build/E2E pipeline, start the full Compose stack with fresh secrets, apply migrations against PostgreSQL, exercise event retry/DLQ behavior against Redpanda, and scan the built frontend in a browser. Reset-password, card payment processing, invitations, and some workspace editing paths are explicitly unavailable; they should remain unavailable states until their service integrations exist.
