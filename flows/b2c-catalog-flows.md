---
artifact: b2c-catalog-flows
status: aspirational
last_modified: 2026-04-29
canon_version: 1
---

# B2C Catalog Flows -- Каталог и карточка товара для покупателя

Описание user flows каталога, поиска, карточки товара и навигации по категориям. B2C не хранит товары -- все данные запрашиваются из B2B по HTTP.

> **Соглашения**: все ID -- UUID (string, format: uuid). Цены -- integer в копейках. Все JSON-поля -- snake_case. Ошибки -- формат `{"code": "...", "message": "..."}`. Пагинация -- `{items, total_count, limit, offset}`.

> **Источник данных**: B2C получает товары из B2B (см. [B2B-7](b2b-flows.md#b2b-7-endpoints-для-b2c-каталог)). Категории -- seed-данные в B2B.

---

## Архитектурные решения

1. **B2C НЕ хранит товары** -- все данные о товарах, SKU, характеристиках, изображениях запрашиваются из B2B по HTTP API. Своя БД B2C: корзина, заказы, избранное.
2. **Условие видимости** -- товар виден покупателю только если `status = MODERATED AND deleted = false AND active_quantity > 0` (хотя бы один SKU с ненулевым остатком). Эту фильтрацию выполняет B2B, не B2C.
3. **Кэширование** -- допускается (Cache-Control), но не обязательно для MVP. Категории меняются редко и могут кэшироваться агрессивнее.
4. **Поиск** -- простой SQL LIKE / pg_trgm через B2B. Elasticsearch не используется.
5. **Рекомендации** -- рандомная выборка из той же категории. ML-модели не используются.

---

<a name="b2c-1-catalog-filters"></a>

## B2C-1: Каталог с фильтрами

### Что происходит

Покупатель открывает категорию товаров, применяет фильтры, выбирает сортировку, листает страницы. B2C проксирует запросы к B2B, который возвращает только видимые товары.

### Шаги покупателя

1. Открыть категорию в меню (или перейти по ссылке)
2. Увидеть список товаров с фото, названием, ценой, наличием
3. (Опционально) Выбрать фильтры в боковой панели (бренд, цвет, цена и др.)
4. (Опционально) Изменить сортировку
5. Листать страницы (пагинация)

### Стыковка с B2B

B2C делает три запроса для отображения страницы категории:

**1. Список товаров:**

```
GET /api/v1/products?category_id={id}&filters[brand]=Apple&sort=price_asc&limit=20&offset=0
```

B2B применяет условие видимости (`status = MODERATED AND deleted = false AND active_quantity > 0`) и возвращает только подходящие товары.

**2. Доступные фильтры для категории:**

```
GET /api/v1/categories/{id}/filters
```

Возвращает список характеристик, по которым можно фильтровать, с возможными значениями.

**3. Фасеты с подсчётом (при изменении фильтров):**

```
GET /api/v1/catalog/facets?category_id={id}&filters[brand]=Apple
```

Возвращает количество товаров для каждого значения фильтра при текущей выборке. Вызывается при каждом изменении фильтров, чтобы обновить счетчики в UI.

### Параметры запроса товаров

| Параметр | Тип | Обязательное | Описание |
|----------|-----|:---:|----------|
| limit | integer | нет | Размер страницы (по умолчанию 20, макс 100) |
| offset | integer | нет | Смещение (по умолчанию 0) |
| category_id | string (uuid) | нет | Фильтр по категории |
| filters | object (deepObject) | нет | Динамические фильтры: `filters[brand]=Apple&filters[color]=черный` |
| sort | string (enum) | нет | Сортировка (см. ниже) |

### Сортировка

| Значение | Описание |
|----------|----------|
| `rating` | По рейтингу (по умолчанию) |
| `popularity` | По популярности |
| `price_asc` | Цена по возрастанию |
| `price_desc` | Цена по убыванию |
| `date_desc` | Сначала новые |
| `discount_desc` | Сначала с максимальной скидкой |

### Response 200 (список товаров)

```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "title": "iPhone 15 Pro Max",
      "image": "https://cdn.neomarket.ru/images/iphone15.jpg",
      "price": 12999000,
      "in_stock": true,
      "is_in_cart": false
    },
    {
      "id": "770e8400-e29b-41d4-a716-446655440003",
      "title": "Samsung Galaxy S24",
      "image": "https://cdn.neomarket.ru/images/s24.jpg",
      "price": 8999000,
      "in_stock": true,
      "is_in_cart": true
    }
  ],
  "total_count": 42,
  "limit": 20,
  "offset": 0
}
```

### Response 200 (фильтры категории)

```json
{
  "items": [
    {
      "slug": "brand",
      "name": "Бренд",
      "type": "list",
      "value": ["Samsung", "Apple", "Xiaomi"]
    },
    {
      "slug": "memory",
      "name": "Объём памяти",
      "type": "list",
      "value": ["64", "128", "256", "512"]
    },
    {
      "slug": "price",
      "name": "Цена",
      "type": "range",
      "min": 999000,
      "max": 15000000
    },
    {
      "slug": "original",
      "name": "Оригинальный товар",
      "type": "switch"
    }
  ]
}
```

### Response 200 (фасеты)

```json
{
  "category_id": "123e4567-e89b-12d3-a456-426614174001",
  "facets": [
    {
      "name": "brand",
      "values": [
        {"value": "Apple", "count": 124},
        {"value": "Samsung", "count": 98},
        {"value": "Xiaomi", "count": 76}
      ]
    },
    {
      "name": "color",
      "values": [
        {"value": "черный", "count": 60},
        {"value": "белый", "count": 40}
      ]
    }
  ]
}
```

### Edge cases

| Ситуация | Поведение |
|----------|-----------|
| Пустая категория (нет товаров) | 200 с пустым `items: []`, `total_count: 0` |
| Нет товаров по фильтрам | 200 с пустым `items: []`. Фронт показывает "Ничего не найдено" с кнопкой сброса фильтров |
| B2B недоступен | 502/503. Фронт показывает "Каталог временно недоступен, попробуйте позже" |
| Несуществующая категория | 404 от B2B. Фронт показывает "Категория не найдена" |
| Невалидный sort | 400 `{"code": "INVALID_REQUEST", "message": "Invalid sort parameter. Allowed: rating, popularity, price_asc, price_desc, date_desc, discount_desc"}` |

---

<a name="b2c-2-search"></a>

## B2C-2: Текстовый поиск

### Что происходит

Покупатель вводит текст в строку поиска. B2C передает запрос в B2B, который ищет по title и description через SQL LIKE / pg_trgm.

### Шаги покупателя

1. Ввести текст в поисковую строку (минимум 3 символа)
2. Нажать Enter или кнопку поиска
3. Увидеть результаты в том же формате, что и каталог (с пагинацией, сортировкой)
4. (Опционально) Применить фильтры к результатам

### Endpoint

```
GET /api/v1/products?search=беспроводные+наушники&limit=20&offset=0&sort=rating
```

Поиск и фильтры совместимы -- можно искать текстом внутри категории:

```
GET /api/v1/products?search=наушники&category_id=123e4567-...&filters[brand]=Sony&sort=price_asc
```

### Поиск на стороне B2B

B2C проксирует параметр `search` в B2B. B2B выполняет поиск по полям `title` и `description` через SQL LIKE / pg_trgm. B2C не имеет собственного поискового индекса.

Условие видимости применяется так же, как в каталоге: `status = MODERATED AND deleted = false AND active_quantity > 0`.

### Response

Тот же формат `ProductShortListResponse`, что и в B2C-1.

### Edge cases

| Ситуация | Поведение |
|----------|-----------|
| Запрос короче 3 символов | 400 `{"code": "INVALID_REQUEST", "message": "Search query must be at least 3 characters"}` |
| Запрос длиннее 255 символов | 400 `{"code": "INVALID_REQUEST", "message": "Search query must be at most 255 characters"}` |
| Пустой результат | 200 с `items: []`, `total_count: 0`. Фронт: "По запросу ничего не найдено" |
| Спецсимволы (`%`, `_`, `'`) | B2B экранирует спецсимволы SQL перед выполнением LIKE-запроса |
| Только стоп-слова | Поиск выполняется как есть (упрощение -- стоп-слова не фильтруются на MVP) |

---

<a name="b2c-3-product-card"></a>

## B2C-3: Карточка товара

### Что происходит

Покупатель открывает страницу конкретного товара. B2C запрашивает полные данные из B2B: описание, изображения, характеристики, список SKU с ценами и остатками.

### Шаги покупателя

1. Кликнуть на товар в каталоге/поиске
2. Увидеть карточку: фото, описание, характеристики товара, список вариаций (SKU)
3. Выбрать вариацию (цвет, размер, объём) -- фронт переключает SKU
4. Увидеть цену, наличие, кнопку "В корзину" для выбранного SKU
5. (Опционально) Пролистать фото, прочитать описание, посмотреть похожие товары

### Endpoint

```
GET /api/v1/products/{id}
```

B2C запрашивает полный Product из B2B. **B2C НЕ хранит товары** -- каждый раз обращается к B2B.

### Выбор SKU

URL содержит `sku_id` как query-параметр (аналог mm.ru):

```
/products/770e8400-e29b-41d4-a716-446655440002?sku=660e8400-e29b-41d4-a716-446655440001
```

При клике на вариацию (цвет, размер) фронт:
1. Меняет `sku` в URL (без перезагрузки страницы)
2. Переключает отображение: цена, остаток, фото текущего SKU
3. Если `sku` не указан в URL -- выбирается первый SKU из списка

Отдельный запрос на SKU не нужен -- все SKU приходят в ответе `GET /products/{id}`.

### Response 200

```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "slug": "iphone-15-pro-max",
  "title": "iPhone 15 Pro Max",
  "description": "Флагманский смартфон Apple 2024 года с чипом A17 Pro",
  "images": [
    {
      "url": "https://cdn.neomarket.ru/images/iphone15-front.jpg",
      "ordering": 0
    },
    {
      "url": "https://cdn.neomarket.ru/images/iphone15-back.jpg",
      "ordering": 1
    }
  ],
  "status": "MODERATED",
  "characteristics": [
    {"name": "Бренд", "value": "Apple"},
    {"name": "Страна-производитель", "value": "Китай"}
  ],
  "skus": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "256GB Black",
      "price": 12999000,
      "discount": 0,
      "image": "/s3/iphone15-black-256.jpg",
      "active_quantity": 10,
      "characteristics": [
        {"name": "Цвет", "value": "Чёрный"},
        {"name": "Объём памяти", "value": "256 ГБ"}
      ]
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "name": "256GB White",
      "price": 12999000,
      "discount": 500000,
      "image": "/s3/iphone15-white-256.jpg",
      "active_quantity": 3,
      "characteristics": [
        {"name": "Цвет", "value": "Белый"},
        {"name": "Объём памяти", "value": "256 ГБ"}
      ]
    }
  ]
}
```

**Примечание**: SKU для B2C не содержит `cost_price` и `reserved_quantity` (см. [B2B-7](b2b-flows.md#b2b-7-endpoints-для-b2c-каталог)).

### Отображение цены со скидкой

Если `discount > 0`, фронт показывает:
- Зачёркнутая цена: `price / 100` руб
- Актуальная цена: `(price - discount) / 100` руб

Пример: `price = 12999000`, `discount = 500000` -> зачёркнуто 129 990 руб, актуальная 124 990 руб.

### Edge cases

| Ситуация | Поведение |
|----------|-----------|
| Товар заблочен/удалён между открытием каталога и кликом | 404 от B2B. Фронт: "Товар недоступен" с кнопкой "Вернуться в каталог" |
| Товар без SKU | Такого не должно быть (status != MODERATED без SKU). Если всё же случилось -- показать товар без кнопки "В корзину" |
| Все SKU с нулевым остатком | Товар не должен попасть в каталог (условие видимости). Если покупатель открыл по прямой ссылке -- показать "Нет в наличии", кнопка "В корзину" неактивна |
| Невалидный `sku` в URL | Игнорировать, выбрать первый SKU из списка |
| SKU с нулевым остатком при наличии других | Показать вариацию, но пометить "Нет в наличии". Кнопка "В корзину" неактивна для этого SKU |
| B2B недоступен | 502/503. Фронт: "Не удалось загрузить товар, попробуйте позже" |

---

<a name="b2c-4-similar-products"></a>

## B2C-4: Похожие товары

### Что происходит

Под карточкой товара отображается блок "Похожие товары" -- выборка из той же категории. Используется рандомная выборка (ML-рекомендации не используются).

### Endpoint

```
GET /api/v1/products/{id}/similar?category={category_id}&limit=8
```

### Параметры

| Параметр | Тип | Обязательное | Описание |
|----------|-----|:---:|----------|
| id | string (uuid) | да (path) | ID текущего товара (исключается из результата) |
| category | string (uuid) | да (query) | ID категории товара |
| limit | integer | нет | Количество (по умолчанию 8, макс 20) |
| offset | integer | нет | Смещение (по умолчанию 0) |

### Алгоритм на стороне B2B

1. Выбрать товары из той же категории (`category_id`) с условием видимости
2. Исключить текущий товар (`id`)
3. Если в категории мало товаров -- расширить на родительскую категорию
4. Вернуть случайную выборку (ORDER BY random() LIMIT N)

### Response 200

```json
{
  "items": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440010",
      "title": "Samsung Galaxy S24 Ultra",
      "image": "https://cdn.neomarket.ru/images/s24u.jpg",
      "price": 11999000,
      "in_stock": true,
      "is_in_cart": false
    },
    {
      "id": "770e8400-e29b-41d4-a716-446655440011",
      "title": "Google Pixel 8 Pro",
      "image": "https://cdn.neomarket.ru/images/pixel8.jpg",
      "price": 7999000,
      "in_stock": true,
      "is_in_cart": false
    }
  ],
  "total_count": 15,
  "limit": 8,
  "offset": 0
}
```

### Edge cases

| Ситуация | Поведение |
|----------|-----------|
| Нет похожих товаров в категории | 200 с `items: []`. Фронт скрывает блок "Похожие товары" |
| Категория не существует | 400 `{"code": "INVALID_REQUEST", "message": "Nonexistent category id"}` |
| Товар не найден | 404 `{"code": "NOT_FOUND", "message": "Product not found"}` |
| В категории только текущий товар | `items: []` (текущий товар исключён) |

---

<a name="b2c-5-category-nav"></a>

## B2C-5: Категории и навигация

### Что происходит

Покупатель видит дерево категорий в боковом меню, навигационную цепочку (breadcrumbs) над списком товаров, и детали категории на странице каталога.

### 5a. Дерево категорий

```
GET /api/v1/categories
```

Возвращает полное дерево категорий для левого меню и навигации. B2B отдаёт плоский список, B2C собирает из него дерево.

#### Response 200

```json
{
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174002",
      "name": "Электроника",
      "parent_id": null,
      "children": [
        {
          "id": "123e4567-e89b-12d3-a456-426614174003",
          "name": "Смартфоны",
          "parent_id": "123e4567-e89b-12d3-a456-426614174002",
          "children": [
            {
              "id": "123e4567-e89b-12d3-a456-426614174004",
              "name": "Android",
              "parent_id": "123e4567-e89b-12d3-a456-426614174003",
              "children": []
            }
          ]
        }
      ]
    },
    {
      "id": "123e4567-e89b-12d3-a456-426614174010",
      "name": "Одежда",
      "parent_id": null,
      "children": []
    }
  ]
}
```

Категории -- seed-данные, меняются редко. B2C может кэшировать это дерево (Cache-Control: max-age=3600).

### 5b. Детали категории

```
GET /api/v1/categories/{id}?include_product_count=true
```

Используется для заголовка страницы категории и SEO.

#### Response 200

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174003",
  "name": "Смартфоны",
  "slug": "smartphones",
  "description": "Мобильные телефоны и смартфоны ведущих производителей",
  "parent": {
    "id": "123e4567-e89b-12d3-a456-426614174002",
    "name": "Электроника",
    "slug": "electronics"
  },
  "product_count": 1542,
  "seo": {
    "title": "Купить смартфон в интернет-магазине | NeoMarket",
    "description": "Смартфоны по выгодным ценам. Бесплатная доставка.",
    "keywords": ["смартфоны", "мобильные телефоны", "купить смартфон"]
  },
  "meta_tags": {
    "og_title": "Смартфоны | NeoMarket",
    "og_description": "Купить смартфон в интернет-магазине."
  },
  "image_url": "https://cdn.neomarket.ru/categories/smartphones.jpg",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-03-01T14:20:00Z"
}
```

### 5c. Фильтры категории

```
GET /api/v1/categories/{id}/filters
```

Список характеристик, по которым можно фильтровать товары в этой категории. Вызывается при открытии страницы категории для построения боковой панели фильтров.

Response -- см. пример в B2C-1.

### 5d. Навигационная цепочка (breadcrumbs)

```
GET /api/v1/breadcrumbs?category_id={id}
GET /api/v1/breadcrumbs?product_id={id}
```

Ровно один параметр: `category_id` или `product_id`. Возвращает массив предков от корня до текущего элемента.

#### Response 200

```json
{
  "data": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174002",
      "slug": "electronics",
      "name": "Электроника",
      "url": "/catalog/electronics",
      "level": 0,
      "is_current": false
    },
    {
      "id": "123e4567-e89b-12d3-a456-426614174003",
      "slug": "smartphones",
      "name": "Смартфоны",
      "url": "/catalog/electronics/smartphones",
      "level": 1,
      "is_current": true
    }
  ],
  "meta": {
    "resolved_via": "category_id",
    "category_id": "123e4567-e89b-12d3-a456-426614174003"
  }
}
```

### Edge cases (категории)

| Ситуация | Поведение |
|----------|-----------|
| Несуществующая категория | 404 `{"code": "NOT_FOUND", "message": "Category not found"}` |
| Сломанная иерархия (orphan node) | 422 `{"error": "orphan_node", "message": "category hierarchy is broken"}` |
| Оба параметра в breadcrumbs | 400 `{"error": "ambiguous_param", "message": "only one of category_id or product_id must be provided"}` |
| Ни одного параметра в breadcrumbs | 400 `{"error": "missing_param", "message": "category_id or product_id must be provided"}` |
| B2B недоступен | 502/503. Для дерева категорий -- можно использовать кэш, если есть |

---

## Сводная таблица эндпоинтов B2C (каталог)

| Flow | Метод | Путь | Описание | Источник данных |
|------|-------|------|----------|----------------|
| B2C-1 | GET | /api/v1/products | Каталог с фильтрами и пагинацией | B2B |
| B2C-1 | GET | /api/v1/categories/{id}/filters | Доступные фильтры для категории | B2B |
| B2C-1 | GET | /api/v1/catalog/facets | Фасеты с подсчётом | B2B |
| B2C-2 | GET | /api/v1/products?search=... | Текстовый поиск | B2B |
| B2C-3 | GET | /api/v1/products/{id} | Карточка товара | B2B |
| B2C-4 | GET | /api/v1/products/{id}/similar | Похожие товары | B2B |
| B2C-5 | GET | /api/v1/categories | Дерево категорий | B2B |
| B2C-5 | GET | /api/v1/categories/{id} | Детали категории | B2B |
| B2C-5 | GET | /api/v1/breadcrumbs | Навигационная цепочка | B2B |

---

## Несоответствия текущей OpenAPI-спеки (catalog/openapi.yaml)

При реализации нужно исправить следующее в `neomarket-protocols/b2c/catalog/openapi.yaml` по [type-unification](type-unification.md):

| Что | Текущее состояние | Как должно быть | Ссылка |
|-----|-------------------|-----------------|--------|
| **Цены** | `type: number`, пример `999.99` | `type: integer`, пример `9999900` (копейки) | type-unification #2 |
| **Image.order** | Поле `order` | Поле `ordering` | type-unification #3 |
| **ProductStatus enum** | `ON_MODERATED` (опечатка) | `ON_MODERATION` | type-unification #6 |
| **ProductStatus enum** | Нет `HARD_BLOCKED` | Добавить `HARD_BLOCKED` | type-unification #6 |
| **Характеристики** | `"COLOR"`, `"BRAND"`, `"MEMORY"` (UPPERCASE) | `"Цвет"`, `"Бренд"`, `"Объём памяти"` (русские из seed-данных) | type-unification #8 |
| **ErrorResponse** | `{"message": "..."}` (без `code`) | `{"code": "...", "message": "..."}` | type-unification #7 |
| **SkuShort** | Нет `id` | Добавить `id` (UUID) -- нужен для навигации по SKU | -- |
| **SKU в Product** | Нет `discount` | Добавить `discount: integer` (копейки) | b2b-flows B2B-7 |
