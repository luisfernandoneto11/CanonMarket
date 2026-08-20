# ADR-014: Order cancellation and B2B unreserve

## Contexto

Cancellation must release the inventory reservation in the B2B inventory service, not only in the B2C process. The buyer may cancel while the order is still operationally cancellable, including orders in `CREATED`, `PAID`, `ASSEMBLING`, or `DELIVERING`. If the downstream release cannot be acknowledged, the intent must be retained as `CANCEL_PENDING`.

## Decisão

`POST /api/v1/orders/{order_id}/cancel` verifies ownership before changing state and allows the four cancellable statuses. It calls `POST /api/v1/inventory/unreserve` through the configured `B2B_URL` or `B2B_INVENTORY_URL`, using `X-Service-Key` and the order id plus item quantities. HTTP 200, 202, and 204 are accepted; unavailable or failed calls transition the order to `CANCEL_PENDING` and record the failure for the existing retry hook. When no B2B URL is configured, the in-memory unreserve remains as a local-development fallback.

The cancellation response uses the complete order snapshot with `buyer_id`, `subtotal`, `total`, `address`, and `created_at`, while retaining legacy aliases for compatibility. Idempotency and ownership behavior remain unchanged, and invalid terminal statuses continue to return 409 with the current status.

## Consequences

Separately deployed B2C and B2B services now use the published inventory path during cancellation, and downstream stock is released before the order becomes `CANCELLED`. A production deployment should use durable outbox/retry storage rather than the in-memory scaffold.
