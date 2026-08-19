# ADR-013: Terminal HARD_BLOCKED product state

## Contexto

Hard blocking is reserved for counterfeit, prohibited, or copyright-infringing products. It is a terminal moderation decision in the normal application flow: a seller must not be able to edit, delete, or add SKUs after the decision, and an incoming EDITED event must not move the product back into moderation.

## Alternatives

The alternatives were a terminal enum status checked by every mutating endpoint, a separate `is_terminal` flag, or moving hard-blocked products into an archive table. The enum status keeps the lifecycle explicit and makes audit queries straightforward; a separate flag risks inconsistent combinations, while an archive table complicates references and emergency data-fixes.

## Decisão

`HARD_BLOCKED` is represented as the product status and is checked by SKU creation, product update, product deletion, approval, and decline operations. The moderation-to-B2B event uses `status=BLOCKED` with `hard_block=true`, a deterministic idempotency key, the blocking reason, and field reports. Incoming `EDITED` events are accepted idempotently but ignored while the product is terminal; an incoming `DELETED` event marks the local moderation representation deleted while preserving the blocked flag that represents the B2B state.

## Consequences

The normal API has no unblock operation. A superadministrator may perform an emergency data-fix through an audited administrative channel, but that operation is intentionally outside this FastAPI flow. The explicit status guard reduces accidental bypass risk and makes the terminal behavior easy to test, while the deterministic outbound event prevents duplicate cascade decisions in B2B.
