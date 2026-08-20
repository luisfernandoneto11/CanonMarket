# ADR-008: Order-aware inventory reservation contract

## Contexto

B2C checkout calls B2B inventory through service-to-service endpoints. A request can contain repeated lines for the same SKU, so checking each line independently can reserve more than the available stock. Once a reservation consumes the final active unit, B2C must be informed that the SKU is out of stock.

## Decisão

The canonical endpoints are `POST /api/v1/inventory/reserve` and `POST /api/v1/inventory/unreserve`. Reserve requests require `order_id`, `idempotency_key`, and item lines. Lines are aggregated by `sku_id` before any stock mutation; if one aggregate exceeds availability, the operation fails atomically and no SKU changes. Successful responses include `order_id`, `reserved`, `reserved_items`, and `failed_items`, while the legacy `items` field remains as a compatibility alias.

Reservation results are cached by `idempotency_key`, and unreserve results by `order_id`. When a SKU reaches zero active stock, B2B records the event and, when `B2C_URL` is configured, posts `SKU_OUT_OF_STOCK` to `/api/v1/events/inventory` with `X-Service-Key`; HTTP 200 and 202 are accepted.

## Consequences

Checkout can use the published inventory paths without relying on legacy aliases. Duplicate SKU lines are safe, retries do not double-deduct inventory, and B2C receives an explicit event for cache/catalog invalidation. A production deployment should back the in-memory idempotency maps and event delivery with durable storage or an outbox.
