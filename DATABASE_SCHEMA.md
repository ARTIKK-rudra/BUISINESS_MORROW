# Database Schema Design

Logical design for PostgreSQL; this is not a migration or implementation. Columns below are indicative. Use UUID primary keys, `created_at`/`updated_at` timestamps, explicit foreign keys, and tenant scoping. Decide exact constraints after workflows and jurisdiction are known.

## Shared conventions

- Tenant-owned records have `business_id`; enforce tenant scope in every API/service query and consider PostgreSQL row-level security as defense in depth after the access model is proven.
- Store timestamps in UTC (`timestamptz`) and retain business timezone on Business for calendars and reporting.
- Store money as `numeric(precision, scale)` with currency code; quantities use suitable decimal precision and a unit of measure.
- Use soft deletion only where recovery/business history requires it. Financial and stock facts should be corrected with compensating entries, not overwritten.
- Add uniqueness for natural identifiers within business (for example SKU, invoice number where appropriate), and indexes on tenant, foreign keys, event time, and common report filters.

## Entities and relationships

| Entity | Key fields / relationships |
|---|---|
| Business | `id`, name, timezone, base currency, settings; tenant root. |
| User | `id`, email/identity subject, status; identity may belong to multiple businesses through membership. |
| Role | `id`, business scope or global role definition, name, permission set. Prefer `BusinessUserRole(business_id,user_id,role_id)` as the membership/assignment join even though it is an additional supporting table. |
| Product | `id`, `business_id`, SKU, name, category, unit, active state, optional barcode. |
| Category | `id`, `business_id`, name, optional parent category. |
| Ingredient | `id`, `business_id`, name, unit, optional linked Product; distinguish stocked raw material from sellable product as requirements dictate. |
| Recipe | `id`, `business_id`, output product, yield quantity/unit, version/effective dates. Supporting `RecipeIngredient(recipe_id,ingredient_id,quantity,unit)` expresses composition. |
| Inventory | `id`, `business_id`, product or ingredient, location, on-hand/reserved quantity, reorder settings; unique item/location. |
| InventoryMovement | `id`, `business_id`, inventory/item, signed quantity, reason, source reference, actor, occurred_at; append-only stock history. |
| Supplier | `id`, `business_id`, name, contact details, status. |
| SupplierProduct | `id`, `business_id`, supplier, product/ingredient, supplier SKU, cost/currency, lead time, MOQ; unique supplier/item. |
| Customer | `id`, `business_id`, optional contact/profile fields, consent/retention state. Minimize personal data. |
| Order | `id`, `business_id`, customer optional, status, placed_at, currency, subtotal/tax/total, idempotency key. |
| OrderItem | `id`, `order_id`, product, quantity, unit price, discounts/tax snapshot, line total; retain price/name snapshots as needed. |
| Payment | `id`, `business_id`, `order_id`, provider reference, amount/currency, status, method, timestamps; unique provider reference. |
| Refund | `id`, `business_id`, payment/order, amount/currency, reason, provider reference, status, created_at. |
| Purchase | `id`, `business_id`, supplier, status, ordered/received dates, currency, total, external reference. |
| PurchaseItem | `id`, `purchase_id`, product/ingredient, ordered/received quantity, unit cost, tax/line total. |
| Expense | `id`, `business_id`, category, amount/currency, occurred_at, payee, invoice/document reference, status. |
| LedgerEntry | `id`, `business_id`, source type/id, account/category, debit/credit or signed amount, currency, occurred_at; immutable postings with reversal links. Accounting model needs domain/jurisdiction review. |
| Invoice | `id`, `business_id`, optional sales `order_id` or supplier `supplier_id`, invoice number, status, issue time, currency, subtotal, tax, and total. Invoice number is unique within a business. |
| InvoiceLine | `invoice_id`, description, quantity, and unit price for the manually verified line items on a supplier invoice. |
| InvoiceCapture | OCR engine, extracted text and editable JSON draft, status, uploader, confirmer, timestamps, and link to the invoice created after confirmation. Drafts are never treated as posted accounting transactions. |
| Forecast | `id`, `business_id`, target type/id, horizon start/end, generated_at, model version, point/quantile values, unit, input cutoff, run id. Consider child rows per target period/quantile for queryability. |
| Prediction | `id`, `business_id`, target type/id, prediction type, probability/value, threshold, model/run reference, generated_at, explanation metadata. |
| Anomaly | `id`, `business_id`, entity type/id, detected_at, score/severity, reason/features summary, status/reviewer. |
| Recommendation | `id`, `business_id`, type, target, suggested quantity/action, assumptions, expected impact, status, provenance, owner approver/time, executed purchase reference. |
| Notification | `id`, `business_id`, recipient, channel, template/payload, status, scheduled/sent times, provider reference, deduplication key. |
| VoiceInteraction | `id`, `business_id`, user, provider/session ref, transcript or protected object reference, intent/result, consent and retention metadata, created_at. Avoid retaining raw audio by default. |

Reorder recommendations include owner approver, approval time, and the resulting purchase reference. The approval endpoint creates the purchase and records the approval in one transaction; repeated approval requests return the same purchase through an idempotency key.
| AuditLog | `id`, `business_id`, actor, action, entity type/id, timestamp, request/correlation id, redacted before/after metadata. Append-only access controls. |

Supporting tables likely needed: `BusinessUserRole`, `Location`, `RecipeIngredient`, `OutboxEvent`, `ModelVersion`, and possibly `ForecastValue`/`PaymentAttempt`. These are structural helpers rather than replacements for requested entities.

## Event names and outbox

Persist event metadata in `OutboxEvent(id, business_id, event_type, schema_version, aggregate_type, aggregate_id, occurred_at, payload, published_at, attempts)`. Write the outbox row in the same transaction as domain changes. Payloads should contain stable IDs, versioned facts, and minimal personal data. A publisher claims unpublished rows safely, retries with backoff, and records delivery; consumers deduplicate by event ID. Retention/partitioning can be added when volume warrants it.

| Event type | Typical source and downstream use |
|---|---|
| `SALE_CREATED` | Order commits; inventory and analytics consume. |
| `PAYMENT_COMPLETED` | Payment provider confirmation; ledger/reporting consume. |
| `REFUND_CREATED` | Refund commits; ledger and demand corrections consume. |
| `PURCHASE_CREATED` | Purchase commits; procurement analytics consume. |
| `INVENTORY_UPDATED` | Movement commits; stock projection and forecast features consume. |
| `STOCK_LOW` | Threshold/rule evaluation; notification and recommendation workflows consume. |
| `STOCK_CRITICAL` | Critical threshold; prioritized alert workflow consumes. |
| `FORECAST_UPDATED` | Forecast run persists; dashboard and optimization consume. |
| `ANOMALY_DETECTED` | Rule/model finding persists; review/notification workflow consumes. |
| `REORDER_RECOMMENDED` | Recommendation persists; dashboard/notification consumes. |
| `NOTIFICATION_CREATED` | Notification intent persists; delivery worker consumes. |

Use consistent uppercase names as requested, but treat event type strings and payload schemas as versioned contracts. Events represent committed facts; commands such as “create sale” are API operations, not events.

## Implemented inventory workflow notes

The current backend stores each inventory row against exactly one product or ingredient and one location. Ingredients and inventory rows carry minimum, maximum, and safety thresholds. `InventoryBatch` records lot code, received/remaining quantities, cost, and optional expiry; `GoodsReceipt` and its lines preserve receipt provenance. `SupplierPriceHistory` records supplier catalog price changes. Recipe ingredient quantities are normalized to each ingredient's base unit when recipes are saved.

Purchase orders are commitments and do not mutate inventory. A goods receipt locks the order and its lines, prevents over-receipt, updates on-hand stock and weighted-average valuation, creates batches and movements, posts inventory/accounts-payable ledger entries, and writes audit/outbox rows in one transaction. Sale processing deducts recipe ingredients when a recipe exists; otherwise it deducts the product itself. Batch consumption uses earliest-expiry-first and rejects expired stock for sales. Rule alerts are derived from thresholds and expiry dates; they are not ML predictions.

## Implemented ML persistence notes

`ModelVersion` stores model type/version, status, dataset kind, feature schema, training/evaluation metrics, artifact URI, timestamps, and metadata. `Forecast` stores per-period point and empirical residual interval values with generation timestamp, model version, and factor/uncertainty provenance. `Prediction` stores stock-out duration/probability with assumption and factor provenance. `Anomaly` stores the unsupervised review score, model version, factors, and the explicit no-ground-truth uncertainty. The current stock-out probability is an uncalibrated normal approximation; anomaly scores are not probabilities.

## Important integrity rules

Order-item totals and invoice/payment amounts require currency-aware reconciliation. A payment provider callback must be idempotent. Receipt of purchase items and sale consumption should create inventory movements. Refunds must not erase sales history. Recipes can translate sold finished products into ingredient demand only if recipe versions and effective dates are captured. Forecast and model provenance must be retained so displayed outputs can be reproduced or investigated.
# Event delivery tables (Phase 7)

- `outbox_events` remains the transactional event source. Delivery state tracks attempt count, retry time, publisher lease, last error, published time, and dead-letter time.
- `event_consumer_receipts` uses `(event_id, consumer_name)` as its primary key; a receipt and consumer side effects commit together.
- `realtime_events` is a tenant-scoped, durable UI projection with a monotonic stream sequence and unique source event ID for SSE replay.
- `realtime_business_metrics` stores event counts and sales/refund/purchase totals grouped by currency; cross-currency amounts are never summed together.
- `ml_event_tasks` records idempotent input refresh work, leases, retries, outcomes, and measured training status for the ML pipeline.
- `notifications.source_event_id` prevents duplicate in-app notices from redelivered events.

The event envelope is specified at `backend/app/events/schemas/business-event-v1.schema.json`. Payloads should exclude credentials and unnecessary personal data. Consumer receipts and realtime events need a retention policy before production scale; DLQ records must be monitored and replayed only after the underlying handler issue is corrected.
