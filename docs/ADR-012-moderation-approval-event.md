# ADR-012: Approval and MODERATED event delivery

## Contexto

When a moderator approves a product, the B2B catalog must receive a `MODERATED` event; otherwise the moderation result would not become visible to buyers. Approval is allowed only for an `IN_REVIEW` card assigned to the current moderator and containing at least one SKU.

## Alternatives

A synchronous POST from the approval handler provides immediate confirmation but couples response time to B2B availability. An outbox pattern improves delivery reliability by persisting events before a background sender runs, while an event bus offers stronger decoupling but adds infrastructure and operational complexity.

## Decisão

The current in-memory MVP uses synchronous event emission through `_emit_moderation_event`. The event has a deterministic idempotency key derived from product, status, and hard-block flag, so retries do not append duplicate catalog decisions. If B2B is unavailable, approval returns `503` and leaves the card in `IN_REVIEW`, allowing the moderator to retry safely.

## Consequências

The implementation is simple and gives the moderator immediate feedback, but production should replace the in-memory event list with a transactional outbox to survive process restarts and guarantee delivery. The B2B event contract is documented in the moderation OpenAPI file and includes the `MODERATED` status without seller-private fields.
