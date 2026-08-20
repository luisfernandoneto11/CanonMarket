# ADR-009: Moderation decision delivery

## Contexto

Moderation sends product decisions to B2B through a service-to-service event channel. The previous route accepted a legacy command-shaped payload and returned JSON, which did not match the published integration contract. A BLOCKED decision must also invalidate the B2C representation so buyer carts and catalog caches do not retain a now-unavailable product.

## Decisão

The canonical endpoint is `POST /api/v1/moderation/events`. Its envelope requires `idempotency_key`, `product_id`, `event_type`, and `occurred_at`; supported event types are `PRODUCT_MODERATED` and `PRODUCT_BLOCKED`. A valid or duplicate event is acknowledged with HTTP 204, while the legacy `/api/v1/events/moderation` JSON endpoint remains only as a compatibility alias.

The local decision remains idempotent by `idempotency_key`. For `PRODUCT_BLOCKED`, B2B applies either `BLOCKED` or terminal `HARD_BLOCKED`, stores the reason and field reports, and publishes a `PRODUCT_BLOCKED` event to B2C at `/api/v1/events/product` when `B2C_URL` is configured. HTTP 200 and 202 are accepted by the delivery client; the event is always recorded locally for the scaffold.

## Consequences

Moderation can call the contract-declared route and receive the expected empty acknowledgement. B2C receives a cross-service invalidation event rather than relying only on local memory. Production deployment should make event delivery durable with an outbox and retry policy.
