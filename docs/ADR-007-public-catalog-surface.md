# ADR-007: Public B2C catalog surface

## Contexto

The B2C integration needs a stable service-to-service surface rather than relying on seller-oriented paths. The published contract requires listing, batch product lookup, public product detail, and public SKU detail under `/api/v1/public/*`.

## Decisão

Expose `GET /api/v1/public/products`, `POST /api/v1/public/products/batch`, `GET /api/v1/public/products/{product_id}`, and `GET /api/v1/public/skus/{sku_id}`. Every operation validates `X-Service-Key`, returns only `MODERATED`, non-deleted products with at least one active SKU, and serializes SKUs through `PublicSkuResponse`. The public serializer excludes `cost_price` and `reserved_quantity`; unavailable or unknown products and SKUs are returned as `404`.

The existing filtered catalog implementation is reused for public listing so pagination, search, category selection, sort, facets, and B2B availability behavior remain consistent. The batch operation preserves requested visibility semantics and omits IDs that are not publicly visible.

## Consequences

B2C clients no longer depend on the seller route `/api/v1/products`. The contract now exposes all four public paths, and adding a future public field requires an explicit serializer and OpenAPI change instead of accidentally returning internal inventory economics.
