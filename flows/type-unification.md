---
artifact: type-unification
status: aligned
last_modified: 2026-04-29
canon_version: 1
---

# Type Unification — Единые типы данных NeoMarket

Обязательные соглашения по типам данных для всех трёх сервисов (B2B, Moderation, B2C). Любое отклонение от этого документа — баг контракта.

---

## 1. UUID для всех ID

**Решение**: все идентификаторы сущностей — `string, format: uuid`.

```yaml
type: string
format: uuid
example: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

Никаких `integer` ID в API. В PostgreSQL — нативный тип `UUID`, генерация через `gen_random_uuid()`.

**Почему:**
- UUID не раскрывает количество записей (безопасность)
- Генерируется на клиенте, нет зависимости от автоинкремента
- Уникален между сервисами — нет коллизий при миграции

---

## 2. Цены в копейках (integer)

**Решение**: все денежные суммы — `integer`, единица измерения — копейки.

```yaml
type: integer
description: "Цена в копейках"
example: 12999000  # = 129 990.00 руб
```

Никаких `float`, `number`, `decimal` в API. Конвертация в рубли — задача фронтенда.

**Почему:**
- `0.1 + 0.2 != 0.3` в float — недопустимо для финансов
- Стандарт индустрии (Stripe, Тинькофф, Ozon)

**Поля**: `price`, `cost_price`, `discount`, `unit_price`, `line_total`, `total_amount`.

---

## 3. Поле `ordering` для порядка изображений

**Решение**: порядок изображений — поле `ordering` (не `order`).

```yaml
ordering:
  type: integer
  description: "Порядок отображения (0 = главное фото)"
  example: 0
```

**Почему**: `order` — зарезервированное слово в SQL (`ORDER BY`), конфликтует с ORM.

---

## 4. snake_case для JSON-полей

**Решение**: все поля в JSON — `snake_case`. Это Python/Django проект.

| Правильно | Неправильно |
|-----------|-------------|
| `product_id` | `productId` |
| `seller_id` | `sellerId` |
| `active_quantity` | `activeQuantity` |
| `reserved_quantity` | `reservedQuantity` |
| `cost_price` | `costPrice` |
| `blocking_reason` | `blockingReason` |
| `field_reports` | `fieldReports` |
| `hard_block` | `hardBlock` |
| `sku_id` | `skuId` |
| `queue_priority` | `queuePriority` |
| `date_created` | `dateCreated` |
| `total_count` | `totalCount` |
| `created_at` | `createdAt` |
| `updated_at` | `updatedAt` |

Единственное исключение: HTTP-заголовки (`X-Service-Key`, `Idempotency-Key`) — в них стандартный HTTP-формат (заглавные через дефис).

---

## 5. camelCase НЕ используем

Даже в событиях (events). Единый стиль `snake_case` во всех JSON-телах запросов и ответов, включая межсервисные callback-и.

---

## 6. Статусы товара (ProductStatus)

```yaml
ProductStatus:
  type: string
  enum:
    - CREATED
    - ON_MODERATION
    - MODERATED
    - BLOCKED
    - HARD_BLOCKED
```

| Статус | Значение |
|--------|----------|
| `CREATED` | Товар создан, SKU ещё нет |
| `ON_MODERATION` | Отправлен на модерацию (первичную или повторную) |
| `MODERATED` | Одобрен модератором, доступен в каталоге |
| `BLOCKED` | Мягкая блокировка, продавец может исправить |
| `HARD_BLOCKED` | Перманентная блокировка, терминальный статус |

> **HARD_BLOCKED** — терминальный статус с точки зрения бизнес-flow. В штатной работе снять нельзя. Суперадмин может отозвать в аварийном порядке через Django Admin (data-fix с audit log).

Допустимые переходы:

```
CREATED -> ON_MODERATION (добавлен первый SKU)
ON_MODERATION -> MODERATED (модератор одобрил)
ON_MODERATION -> BLOCKED (модератор отклонил, мягко)
ON_MODERATION -> HARD_BLOCKED (модератор отклонил, жёстко)
MODERATED -> ON_MODERATION (продавец изменил товар)
BLOCKED -> ON_MODERATION (продавец исправил и отправил заново)
```

---

## 7. Единый формат ошибок (Error Response)

Все сервисы возвращают ошибки в одном формате:

```json
{
  "code": "ERROR_CODE",
  "message": "Человекочитаемое описание ошибки"
}
```

```yaml
ErrorResponse:
  type: object
  required:
    - code
    - message
  properties:
    code:
      type: string
      description: "Машиночитаемый код ошибки (UPPER_SNAKE_CASE)"
      example: "PRODUCT_NOT_FOUND"
    message:
      type: string
      description: "Описание ошибки для отладки"
      example: "Товар не найден"
```

Стандартные коды:

| Код | HTTP | Описание |
|-----|------|----------|
| `INVALID_REQUEST` | 400 | Невалидные данные |
| `UNAUTHORIZED` | 401 | Нет авторизации / невалидный X-Service-Key |
| `FORBIDDEN` | 403 | Нет прав (напр., товар HARD_BLOCKED) |
| `NOT_FOUND` | 404 | Ресурс не найден |
| `CONFLICT` | 409 | Конфликт состояния (напр., товар изменён, резерв не прошёл) |
| `UNPROCESSABLE_ENTITY` | 422 | Бизнес-валидация не пройдена |
| `SERVICE_UNAVAILABLE` | 503 | Зависимый сервис недоступен |

---

## 8. Характеристики: `{ "name": "...", "value": "..." }`

**Решение**: единый формат без `id`. Названия на русском (из справочника seed-данных).

```yaml
CharacteristicValue:
  type: object
  required:
    - name
    - value
  properties:
    name:
      type: string
      description: "Название характеристики из справочника"
      example: "Бренд"
    value:
      type: string
      description: "Значение характеристики"
      example: "Apple"
```

Примеры:

```json
{"name": "Бренд", "value": "Apple"}
{"name": "Цвет", "value": "Чёрный"}
{"name": "Объём памяти", "value": "256 ГБ"}
{"name": "Размер", "value": "42"}
```

Никаких UPPERCASE (`"COLOR"`, `"BRAND"`) — только русские названия из seed-данных.

---

## 9. Пагинация

Единый формат для всех списочных endpoint-ов:

```json
{
  "items": [...],
  "total_count": 42,
  "limit": 20,
  "offset": 0
}
```

```yaml
PaginatedResponse:
  type: object
  required:
    - items
    - total_count
    - limit
    - offset
  properties:
    items:
      type: array
      description: "Элементы текущей страницы"
    total_count:
      type: integer
      description: "Общее количество элементов (для расчёта страниц)"
      example: 42
    limit:
      type: integer
      description: "Размер страницы"
      example: 20
    offset:
      type: integer
      description: "Смещение от начала"
      example: 0
```

Query-параметры: `?limit=20&offset=0`. По умолчанию: `limit=20`, `offset=0`. Максимум `limit=100`.

---

## Сводная таблица: что было / что стало

| # | Решение | Было (ошибки в контрактах) | Стало (единый стандарт) |
|---|---------|---------------------------|------------------------|
| 1 | UUID | `integer` в B2B | `string, format: uuid` везде |
| 2 | Копейки | `number: 999.99` в B2C | `integer: 9999900` везде |
| 3 | ordering | `order` в B2C | `ordering` везде |
| 4 | snake_case | `productId`, `sellerId` в events | `product_id`, `seller_id` везде |
| 5 | Без camelCase | `blockingReason`, `fieldReports` | `blocking_reason`, `field_reports` |
| 6 | Статусы | `ON_MODERATED` (опечатка), нет `HARD_BLOCKED` | Полный enum из 5 значений |
| 7 | Ошибки | Разный формат (`{"error": "..."}`) | `{"code": "...", "message": "..."}` |
| 8 | Характеристики | `"COLOR"`, `"BRAND"` + id | `"Бренд"`, `"Цвет"` без id |
| 9 | Пагинация | `page/size`, `totalCount` | `limit/offset`, `total_count` |
