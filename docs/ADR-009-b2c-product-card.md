# ADR-009: Safe B2C product-card representation

## Context

The B2C product card is a buyer-facing response assembled from B2B data. It must include product description, images, characteristics, prices, discounts, and every SKU, while never exposing seller-only fields such as `cost_price`, `reserved_quantity`, `seller_id`, or moderation diagnostics.

## Alternatives considered

One option is a separate serializer/model for B2C, another is filtering fields inside the view, and a third is exposing the B2B model directly and relying on clients to ignore sensitive properties. The direct-model option has the highest accidental-leak risk, while view-level filtering is easy to bypass when a field is added. The implementation therefore uses an explicit `ProductCardResponse` and `ProductCardSkuResponse` model at the public boundary; new seller fields are not serialized unless deliberately added to the public model.

## Decision

Unauthenticated `GET /api/v1/products/{id}` returns the explicit public card only for MODERATED, non-deleted products. A blocked or deleted product returns 404. Every SKU remains visible in the card, including zero-stock SKUs, and each SKU exposes `in_stock` computed from the current active quantity. Seller JWT and moderation service-key requests retain the existing B2B behavior.

## Consequences

The public contract is safer and easier to review, at the cost of maintaining a second response model when fields change. Discount remains an integer in kopecks so clients can render the crossed-out and effective prices without receiving seller cost data.
