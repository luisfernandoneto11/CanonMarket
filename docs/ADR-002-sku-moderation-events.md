# ADR-002: SKU contract and moderation events

## Contexto

A SKU is a seller-owned variant of a product. The B2B contract uses `name`, integer monetary values in kopecks, an array of image objects, and explicit `active_quantity` and `reserved_quantity` inventory fields. Adding the first SKU makes a `CREATED` product enter moderation, while adding a SKU to an already `MODERATED` or soft-`BLOCKED` product requires a new review.

## Decisão

The API accepts `POST /api/v1/skus` only for the authenticated product owner and rejects a terminal `HARD_BLOCKED` product. The first SKU emits `PRODUCT_CREATED`; a SKU added to a `MODERATED` or `BLOCKED` product emits `PRODUCT_EDITED` and changes the product to `ON_MODERATION`. Every event carries top-level `product_id`, `seller_id`, `event_type`, and `json_after`, with a UUID idempotency key. The SKU response uses `images[]` and returns the complete inventory and audit fields required by the OpenAPI contract.

## Consequências

The in-memory implementation records events locally and optionally forwards them to `MODERATION_URL`, accepting both HTTP 200 and 202 as successful responses. Production deployment should place durable event delivery behind an outbox or equivalent retry mechanism. JWT signature verification remains the responsibility of the authenticated service boundary; this local scaffold extracts the seller claim and enforces product ownership.
