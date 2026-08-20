# ADR-012: Ticket approval and B2B decision delivery

## Contexto

The moderation contract identifies approval operations by ticket, not by a product route. A successful approval must return the complete ticket snapshot so clients can update queue state without another lookup. The decision must also reach B2B, otherwise the product remains unpublished in the seller service.

## Decisão

Expose `POST /api/v1/tickets/{ticket_id}/approve` with moderator identity taken from the Bearer token. The request accepts `comment` up to 2000 characters, while the older `moderator_comment` field remains a compatibility alias. The response is `TicketResponse` containing `id`, `product_id`, `seller_id`, `kind`, `status`, `queue_priority`, and `created_at`.

Approval is allowed only for an assigned `IN_REVIEW` ticket that contains at least one SKU. A ticket assigned to another moderator returns 409, and unknown ticket identifiers return 404. The outgoing B2B event uses a deterministic idempotency key and the envelope `event_type`, `occurred_at`, and `payload`, and is posted to `/api/v1/moderation/events` when `B2B_URL` is configured. HTTP 200, 202, and 204 are accepted from B2B; an unavailable destination returns 503 while the product remains in review.

## Consequences

Moderation clients can use the published ticket path and receive a complete, stable response. B2B receives `PRODUCT_MODERATED` reliably within the scaffold’s synchronous delivery model, and repeated approvals do not append duplicate local events. Production deployment should replace the in-memory event list with an outbox and durable retry mechanism.
