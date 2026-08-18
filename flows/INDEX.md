---
artifact: flows-index
status: aligned
last_modified: 2026-04-29
canon_version: 1
---

# NeoMarket Flows — Индекс

Каталог каноничных user flows маркетплейса NeoMarket. Flows здесь — **ЗАКОН**: если твой сервис реализует один из этих flows, он обязан следовать описанным контрактам.

> **Соглашения по типам** — общие для всех flows: [type-unification.md](type-unification.md)  
> **Межсервисные события** — схемы 8 событий: [events-schema.md](events-schema.md)  
> **Аутентификация** — JWT + refresh rotation: [auth-flows.md](auth-flows.md)

---

## Навигация

| Файл | Домен | Flows | Статус |
|------|-------|-------|--------|
| [b2b-flows.md](b2b-flows.md) | B2B кабинет продавца | B2B-1..13 | aspirational |
| [moderation-flows.md](moderation-flows.md) | Очередь модерации | MOD-1..6 | aspirational |
| [b2c-catalog-flows.md](b2c-catalog-flows.md) | Каталог и карточка товара | B2C-1..5 | aspirational |
| [b2c-cart-flows.md](b2c-cart-flows.md) | Корзина, Избранное, Главная | B2C-6..8, B2C-14..15 | aspirational |
| [b2c-orders-flows.md](b2c-orders-flows.md) | Заказы | B2C-9..13 | aspirational |
| [admin-flows.md](admin-flows.md) | Django Admin всех сервисов | ADM-B2B-1..5, ADM-MOD-1..4, ADM-B2C-1..4 | aspirational |
| [events-schema.md](events-schema.md) | Межсервисные события | EVT-1..3 | aspirational |
| [auth-flows.md](auth-flows.md) | Аутентификация | AUTH-1..5 | aspirational |
| [user-stories.md](user-stories.md) | Продуктовые user stories | US-B2B-01..12, US-MOD-01..06, US-CAT-01..05, US-CART-01..05, US-ORD-01..05, US-ADM-*, US-EVT-01..03 | aspirational |
| [type-unification.md](type-unification.md) | Единые типы данных | — | aligned |

---

## Диаграммы

Всего mermaid-блоков в flows/:

| Файл | Диаграммы |
|------|-----------|
| [b2b-flows.md](b2b-flows.md) | Product lifecycle (B2B-5), SKU quantity state (B2B-8), Reserve sequence all-or-nothing (B2B-8) |
| [b2c-orders-flows.md](b2c-orders-flows.md) | Order state machine, Checkout sequence с idempotency (B2C-9), Cancel+CANCEL_PENDING (B2C-11), Fulfill (B2C-13) |
| [b2c-cart-flows.md](b2c-cart-flows.md) | Merge activity (B2C-8 гость→авторизованный) |
| [events-schema.md](events-schema.md) | B2B→Mod, Mod→B2B, B2B→B2C — все три с outbox + retry + replay |
| [moderation-flows.md](moderation-flows.md) | Moderation card lifecycle state machine |
| [auth-flows.md](auth-flows.md) | JWT refresh rotation + blacklist (AUTH-4) |

**Политика**: mermaid дополняет ASCII, не заменяет. ASCII сохраняется для grep-friendly поиска. Mermaid рендерится нативно в GitHub.

---

## Policy: Flow-ID — append-only

**Правило**: идентификаторы (`B2B-N`, `MOD-N`, `B2C-N`, `AUTH-N`, `ADM-*-N`, `EVT-N`, `US-*-NN`) — **append-only**. При изменении/удалении flow — пометить `⚠ deprecated` в заголовке и оставить запись; не переименовывать, не перенумеровывать.

**Новые flows**: получают следующий ID (например, `B2B-14`, `MOD-7`), не переиспользуют освободившиеся номера.

---

## B2B — Кабинет продавца

Документ: [b2b-flows.md](b2b-flows.md)

| # | Flow | Endpoint |
|---|------|----------|
| B2B-1 | Создание товара | `POST /api/v1/products` |
| B2B-2 | Создание SKU | `POST /api/v1/skus` |
| B2B-3 | Редактирование товара/SKU | `PUT /api/v1/products/{id}`, `PUT /api/v1/skus/{id}` |
| B2B-4 | Удаление товара | `DELETE /api/v1/products/{id}` |
| B2B-5 | Просмотр товара (+ статус блокировки) | `GET /api/v1/products/{id}` |
| B2B-6 | Создание и приёмка накладной | `POST /api/v1/invoices`, `POST /api/v1/invoices/{id}/accept` |
| B2B-7 | Endpoints для B2C (каталог) | `GET /api/v1/products` (public) |
| B2B-8 | Reserve / Unreserve (для B2C) | `POST /api/v1/reserve`, `POST /api/v1/unreserve` |
| B2B-9 | Обработка событий от Moderation | `POST /api/v1/events/moderation` |
| B2B-10 | Fulfill (списание резерва при DELIVERED) | `POST /api/v1/fulfill` |
| B2B-11 | Список товаров продавца | `GET /api/v1/products` (seller) |
| B2B-12 | Удаление SKU | `DELETE /api/v1/skus/{id}` |
| B2B-13 | Загрузка изображения | `POST /api/v1/images`, `DELETE /api/v1/images/{id}` |

---

## Moderation — Очередь модерации

Документ: [moderation-flows.md](moderation-flows.md)

| # | Flow | Endpoint |
|---|------|----------|
| MOD-1 | Получение события от B2B | `POST /api/v1/events/product` |
| MOD-2 | Получение карточки из очереди | `POST /api/v1/product-moderation/get-next` |
| MOD-3 | Одобрение товара | `POST /api/v1/products/{id}/approve` |
| MOD-4 | Мягкая блокировка | `POST /api/v1/products/{id}/decline` |
| MOD-5 | Жёсткая блокировка | `POST /api/v1/products/{id}/decline` (hard_block) |
| MOD-6 | Справочник причин блокировки | `GET /api/v1/product-blocking-reasons` |

---

## B2C — Каталог + Карточка товара

Документ: [b2c-catalog-flows.md](b2c-catalog-flows.md)

| # | Flow | Endpoint |
|---|------|----------|
| B2C-1 | Каталог с фильтрами и пагинацией | `GET /api/v1/products`, `GET /api/v1/categories/{id}/filters` |
| B2C-2 | Текстовый поиск | `GET /api/v1/products?search=...` |
| B2C-3 | Карточка товара | `GET /api/v1/products/{id}` |
| B2C-4 | Похожие товары | `GET /api/v1/products/{id}/similar` |
| B2C-5 | Категории (дерево, детали, фильтры, breadcrumbs) | `GET /api/v1/categories`, `GET /api/v1/breadcrumbs` |

---

## B2C — Корзина + Избранное

Документ: [b2c-cart-flows.md](b2c-cart-flows.md)

| # | Flow | Endpoint |
|---|------|----------|
| B2C-6 | Избранное (CRUD) | `GET/POST/DELETE /api/v1/favorites/{product_id}` |
| B2C-7 | Подписки на товар | `POST /api/v1/favorites/{product_id}/subscribe` |
| B2C-8 | Корзина (CRUD, обогащение из B2B, merge гостевой) | `GET/POST/PUT/DELETE /api/v1/cart` |

---

## B2C — Заказы

Документ: [b2c-orders-flows.md](b2c-orders-flows.md)

| # | Flow | Endpoint |
|---|------|----------|
| B2C-9 | Checkout → Создание заказа | `POST /api/v1/orders` |
| B2C-10 | Просмотр и отслеживание заказов | `GET /api/v1/orders`, `GET /api/v1/orders/{id}` |
| B2C-11 | Отмена заказа | `POST /api/v1/orders/{id}/cancel` |
| B2C-12 | Обработка событий от B2B | `POST /api/v1/events/product` |
| B2C-13 | Fulfill (списание резерва при DELIVERED) | `POST /api/v1/fulfill` (к B2B) |

---

## B2C — Главная страница

| # | Flow | Endpoint |
|---|------|----------|
| B2C-14 | Баннеры на главной | `GET /api/v1/banners` |
| B2C-15 | Подборки товаров | `GET /api/v1/collections`, `GET /api/v1/collections/{id}` |

---

## Межсервисные события

Документ: [events-schema.md](events-schema.md)

| # | Направление | События |
|---|-------------|---------|
| EVT-1 | B2B → Moderation | CREATED, EDITED, DELETED |
| EVT-2 | Moderation → B2B | MODERATED, BLOCKED |
| EVT-3 | B2B → B2C | PRODUCT_BLOCKED, PRODUCT_DELETED, SKU_OUT_OF_STOCK |

---

## Admin (Django Admin)

Документ: [admin-flows.md](admin-flows.md)

| Домен | Flows |
|-------|-------|
| B2B Admin | ADM-B2B-1 (накладные), ADM-B2B-2 (категории), ADM-B2B-3 (характеристики), ADM-B2B-4 (аварийное управление), ADM-B2B-5 (SKU/остатки) |
| Moderation Admin | ADM-MOD-1 (справочник блокировок), ADM-MOD-2 (очередь), ADM-MOD-3 (разблокировка), ADM-MOD-4 (статистика) |
| B2C Admin | ADM-B2C-1 (статусы заказов), ADM-B2C-2 (подборки), ADM-B2C-3 (баннеры), ADM-B2C-4 (корзины/избранное) |

---

## Сводка покрытия

| Категория | Всего flows | Статус |
|-----------|-------------|--------|
| B2B | 13 | ✅ aspirational |
| Moderation | 6 | ✅ aspirational |
| B2C Каталог | 5 | ✅ aspirational |
| B2C Корзина | 3 | ✅ aspirational |
| B2C Заказы | 5 | ✅ aspirational |
| B2C Главная | 2 | ✅ aspirational |
| Events | 3 | ✅ aspirational |
| Admin B2B | 5 | ✅ aspirational |
| Admin Moderation | 4 | ✅ aspirational |
| Admin B2C | 4 | ✅ aspirational |
| Auth | 5 | ✅ aspirational |
| **Итого** | **55** | |
