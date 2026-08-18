# ADR-008: B2C catalog filters and facets

## Context

The B2C catalog must expose only products that are MODERATED, not deleted, and have at least one SKU with positive active stock. Search, category, batch-id, pagination, and characteristic filters are applied to the live B2B product data. Facets must describe the currently visible result set rather than a stale catalog snapshot.

## Decision

The catalog keeps `X-Service-Key` as its inter-service authentication mechanism and evaluates visibility and filters on every request. Dynamic characteristic filters use the OpenAPI deep-object query convention (`filters[Brand]=Apple`). Facets are computed from visible products and return deterministic, sorted value counts. Public responses intentionally omit seller-sensitive fields such as `cost_price`, `reserved_quantity`, `seller_id`, and moderation diagnostics.

## Alternatives considered

A separate B2C read model would provide lower latency but would require synchronization and could expose stale stock. A cached facet index would reduce computation but would become inconsistent after moderation or inventory changes. The in-memory live evaluation is selected for this MVP because it preserves correctness and makes the B2B dependency boundary explicit; a read model can be introduced when operational scale requires it.

## Failure behavior

If the B2B catalog dependency is unavailable, catalog and facet requests return the canonical `502 B2B_UNAVAILABLE` error rather than partial data. No reservation or mutation is performed by catalog reads.

## Consequences

The implementation is simple and consistent with the canonical flow, while the service-key boundary and public response models prevent accidental exposure of seller data. The trade-off is that production scale will require a persistent read model or cache with an explicit freshness policy.
