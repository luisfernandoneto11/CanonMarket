# ADR-010: Checkout idempotency and fixed-price orders

## Contexto

Checkout is the point at which inventory is reserved and an order is created. A repeated client request must not reserve the same SKU or create a second paid order, and a failed multi-SKU reservation must not consume stock partially. Order items also need historical snapshots because B2B prices and product names may change after purchase.

## Alternativas

A unique `idempotency_key` column on the orders table provides a durable constraint, a separate idempotency table or cache isolates keys from orders, and Redis offers distributed coordination with expiry. The database constraint is the simplest durable option for this service, while Redis would add operational complexity and the separate cache would require a second consistency boundary.

## Decisão

The in-memory MVP uses `orders_by_idempotency` as the equivalent of a unique order index: the key is checked before B2B work and the existing order is returned with HTTP 200. In a persistent implementation this map must become a unique database index on `orders.idempotency_key`, with the create operation performed in one transaction so a race between two requests results in one winner and one lookup of the committed order. Reservation is validated and executed all-or-nothing before order creation; `OrderItem` stores `unit_price`, `product_title`, `sku_name`, quantity, and line total as immutable purchase snapshots.

## Consequências

Retries are safe and do not double-reserve inventory. A process-local map is sufficient for the current testable in-memory service but is not a multi-worker durability guarantee; production deployment must replace it with a transactional unique constraint or an equivalent distributed store. The frontend clears the cart only after the checkout request succeeds.
