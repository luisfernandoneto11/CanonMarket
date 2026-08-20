# ADR-013: Irreversible ticket hard block

## Contexto

A hard block is a terminal moderation decision. It must not be confused with an ordinary decline, and an independent B2B service must receive the decision so it can prevent publication and future inventory mutations. B2B product edits arriving after the terminal decision must be acknowledged but ignored.

## Decisão

Expose `POST /api/v1/tickets/{ticket_id}/block` with moderator identity from the Bearer token. The request requires `blocking_reason` and `hard_block: true`, and may include `comment` and field reports. Only an assigned `IN_REVIEW` ticket can transition to `HARD_BLOCKED`; terminal or otherwise invalid transitions are rejected. The response is a complete `TicketResponse`.

After the local transition, B2B receives `PRODUCT_BLOCKED` at `/api/v1/moderation/events` with `event_type`, `occurred_at`, and `payload` containing `status: BLOCKED` and `hard_block: true`. The event uses a deterministic idempotency key and accepts B2B HTTP 200, 202, or 204 responses. The moderation service also exposes `POST /api/v1/b2b/events`, accepting the wrapped `PRODUCT_CREATED`, `PRODUCT_EDITED`, and `PRODUCT_DELETED` envelope; `PRODUCT_EDITED` is explicitly ignored for a `HARD_BLOCKED` product.

## Consequences

The contract paths now work for separately deployed Moderation and B2B services, and a hard-blocked product cannot be accidentally reopened by a later edit event. Durable production delivery should use an outbox and retry worker rather than the in-memory scaffold.
