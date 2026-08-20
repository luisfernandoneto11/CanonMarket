# ADR-005: Product detail visibility boundary

## Contexto

The product-detail endpoint serves two trusted audiences. An authenticated seller may inspect the complete product owned by that seller, including moderation diagnostics and internal SKU economics. A service-key caller receives the public projection used by the storefront and must not receive procurement cost or reserved inventory.

## Decisão

The endpoint keeps one URL but selects the representation from the authenticated access mechanism. Seller access returns `ProductResponse`, including `category_id`, `slug`, `created_at`, `updated_at`, `blocking_reason`, `field_reports`, `cost_price`, and `reserved_quantity`. Service-key access returns `PublicProductDetailResponse`; its nested `PublicSkuResponse` intentionally excludes `cost_price` and `reserved_quantity`, as well as seller-only diagnostics.

The seller path preserves IDOR protection by returning `404` for a product owned by another seller. The service-key path validates the key before serialization and can inspect products across sellers without exposing internal economics.

## Consequences

The OpenAPI contract documents both representations with `oneOf`. Adding a new internal field requires an explicit decision about whether it belongs in the public serializer; it is never exposed accidentally by returning the internal model directly.
