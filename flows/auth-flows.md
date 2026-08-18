---
artifact: auth-flows
status: aspirational
last_modified: 2026-04-29
canon_version: 1
---

# Auth Flows — Аутентификация и JWT в NeoMarket

Единые flows аутентификации для всех трёх сервисов (B2B, Moderation, B2C). JWT самодостаточен: каждый сервис проверяет подпись локально и не ходит в auth-service на каждый запрос.

> **Соглашения**: все ID — UUID. Все поля — snake_case. Время — ISO 8601 (или unix timestamp в JWT). Формат ошибок — `{code, message}` (см. [type-unification.md](type-unification.md)).

---

## 0. Базовые принципы

### 0.1. Где живёт аутентификация

| Сервис | Кто регистрируется / логинится | Endpoint базис |
|--------|--------------------------------|----------------|
| **B2B** | Продавцы (seller) | `/api/v1/auth/*` в B2B |
| **B2C** | Покупатели (buyer) | `/api/v1/auth/*` в B2C |
| **Moderation** | Модераторы, админы | логинятся через admin-панель; регистрация — только через seed / админа |

Каждый сервис держит свою таблицу `users` (независимые пулы). Общий контракт на JWT: подпись + claims одинаковые, public key (или shared secret) синхронизирован через env.

### 0.2. Самодостаточный токен

Каждый из 3 сервисов **сам проверяет** подпись JWT и читает claims. Никаких походов в auth-service на каждый запрос — это ключевой архитектурный выбор:

- **плюсы**: нет SPOF, нет сетевого ходока, сервис автономен;
- **минусы**: инвалидация — не мгновенная (до `exp`), отзыв токена — через blacklist refresh.

Blacklist хранится только для **refresh-токенов** (их мало, TTL 30 дней). Access-токены (1 час) не blacklist-им — полагаемся на короткий TTL.

### 0.3. JWT vs X-Service-Key

| Механизм | Для кого | Где описан |
|----------|----------|------------|
| **JWT** (Bearer) | End-users: seller, buyer, moderator, admin | этот файл |
| **X-Service-Key** | Межсервисные вызовы (B2B -> Moderation и т.д.) | [events-schema.md](events-schema.md) |

Эти механизмы не смешиваются. Сервис-сервис ходит с `X-Service-Key`, пользователь — с `Authorization: Bearer <jwt>`.

---

## 1. JWT: структура и подпись

### 1.1. Claims (payload)

```json
{
  "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "role": "seller",
  "iat": 1760000000,
  "exp": 1760003600,
  "jti": "f9e8d7c6-b5a4-3210-fedc-ba0987654321"
}
```

| Поле | Тип | Обязательное | Описание |
|------|-----|:---:|----------|
| `sub` | string (uuid) | да | ID пользователя (user_uuid) |
| `role` | string (enum) | да | `seller`, `buyer`, `moderator`, `admin` |
| `iat` | integer (unix ts) | да | Issued At — когда выдан |
| `exp` | integer (unix ts) | да | Expiration — когда истекает |
| `jti` | string (uuid) | да | JWT ID — уникальный идентификатор токена (для blacklist) |

**Почему минимум claims:**
- `email`, `first_name` и т.д. — меняются. Хранить в токене = рассинхрон. Сервис, которому нужно больше — дёрнет `/api/v1/users/me` или свою локальную таблицу по `sub`.
- Чем меньше claims — тем меньше размер заголовка (токен ездит в каждом запросе).

### 1.2. Роли (enum)

```yaml
UserRole:
  type: string
  enum:
    - seller      # продавец в B2B
    - buyer       # покупатель в B2C
    - moderator   # модератор в Moderation
    - admin       # суперпользователь (видит всё, управляет модераторами)
```

Авторизация на endpoint-ах проверяет `role`. Пример: `POST /api/v1/products` в B2B требует `role == "seller"`; любой другой — 403 `FORBIDDEN`.

### 1.3. Алгоритм подписи

| Окружение | Алгоритм | Ключ |
|-----------|----------|------|
| **Прод** (целевой) | `RS256` (RSA, asymmetric) | private key — только в auth-service; public key — во всех сервисах через env |
| **Учебный проект / dev** | `HS256` (HMAC, symmetric) | shared secret в `JWT_SECRET` env во всех сервисах |

**Почему так:**
- `RS256` — каждый сервис может проверить, но не выпустить токен. Хороший продакшен-дефолт.
- `HS256` — проще в dev: один `.env`, все сервисы его читают. Для учебного проекта хватает.

Переключение — через env `JWT_ALGORITHM` (`HS256` / `RS256`) и соответственно `JWT_SECRET` или `JWT_PUBLIC_KEY`/`JWT_PRIVATE_KEY`.

### 1.4. TTL

| Токен | TTL | Где хранится на клиенте |
|-------|-----|-------------------------|
| `access_token` | **1 час** (3600 сек) | memory / httpOnly cookie |
| `refresh_token` | **30 дней** (2_592_000 сек) | httpOnly cookie / secure storage |

Access короткий — чтобы компрометация не стоила слишком дорого. Refresh длинный — чтобы пользователь не логинился каждый час.

### 1.5. Проверка токена на каждом сервисе (псевдокод)

```python
# middleware / DRF authentication
def authenticate(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None  # анонимный запрос, дальше — permission check
    token = header[7:]
    try:
        claims = jwt.decode(
            token,
            key=PUBLIC_KEY_OR_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed(code="TOKEN_EXPIRED", message="Токен истёк")
    except jwt.InvalidTokenError:
        raise AuthenticationFailed(code="INVALID_TOKEN", message="Невалидный токен")
    return User(id=claims["sub"], role=claims["role"])
```

Локальная таблица `users` содержит только то, что сервису нужно (например, B2B: `id`, `email`, `company_name`, `inn`). Никаких походов в auth-service на чтение пользователя — поле `id` совпадает с `sub` в JWT.

---

## 2. AUTH-1: Регистрация продавца (B2B)

### Endpoint

```
POST /api/v1/auth/register
Host: {b2b_url}
Content-Type: application/json
```

### Request

```json
{
  "email": "seller@example.com",
  "password": "SecurePass123!",
  "company_name": "ООО Пример",
  "inn": "7707083893",
  "first_name": "Имя",
  "last_name": "Фамилия",
  "phone": "+79001234567"
}
```

| Поле | Тип | Обязательное | Валидация |
|------|-----|:---:|-----------|
| `email` | string | да | RFC 5322, уникален в таблице B2B.users |
| `password` | string | да | минимум 8 символов, 1 цифра, 1 буква |
| `company_name` | string | да | 1..255 символов |
| `inn` | string | да | 10 или 12 цифр, валидная контрольная сумма |
| `first_name` | string | да | 1..100 символов |
| `last_name` | string | да | 1..100 символов |
| `phone` | string | нет | E.164 формат |

### Response 201 Created

```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | string (uuid) | ID созданного продавца (равен `sub` в JWT) |
| `access_token` | string (jwt) | JWT с `role: "seller"` |
| `refresh_token` | string (jwt) | Refresh, TTL 30 дней |
| `token_type` | string | всегда `"Bearer"` |
| `expires_in` | integer | TTL access-токена в секундах |

### Ошибки

| HTTP | code | Когда |
|------|------|-------|
| 400 | `INVALID_REQUEST` | Невалидные поля (плохой email, короткий пароль, неверный ИНН) |
| 409 | `EMAIL_ALREADY_EXISTS` | Email уже зарегистрирован |
| 409 | `INN_ALREADY_EXISTS` | ИНН уже зарегистрирован |

### Что делает сервис

1. Валидирует поля (включая контрольную сумму ИНН).
2. Проверяет уникальность `email` и `inn` в B2B.users.
3. Хеширует пароль (`argon2` или `bcrypt`).
4. Создаёт запись в B2B.users (status = `active`).
5. Генерирует пару токенов (access + refresh).
6. Записывает `refresh.jti` в таблицу `refresh_tokens` (для blacklist-проверок).
7. Возвращает `201` с токенами.

---

## 3. AUTH-2: Регистрация покупателя (B2C)

### Endpoint

```
POST /api/v1/auth/register
Host: {b2c_url}
Content-Type: application/json
```

### Request

```json
{
  "email": "buyer@example.com",
  "password": "SecurePass123!",
  "first_name": "Имя",
  "last_name": "Фамилия",
  "phone": "+79009876543"
}
```

| Поле | Тип | Обязательное | Валидация |
|------|-----|:---:|-----------|
| `email` | string | да | RFC 5322, уникален в таблице B2C.users |
| `password` | string | да | минимум 8 символов, 1 цифра, 1 буква |
| `first_name` | string | да | 1..100 символов |
| `last_name` | string | да | 1..100 символов |
| `phone` | string | нет | E.164 формат |

### Response 201 Created

```json
{
  "user_id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

JWT содержит `role: "buyer"`.

### Ошибки

| HTTP | code | Когда |
|------|------|-------|
| 400 | `INVALID_REQUEST` | Невалидные поля |
| 409 | `EMAIL_ALREADY_EXISTS` | Email уже зарегистрирован в B2C |

---

## 4. AUTH-3: Логин

Одинаковый контракт для B2B и B2C — **разные endpoint-ы, разные пулы пользователей**. Продавец не может залогиниться в B2C (там его просто нет) и наоборот.

### Endpoint (B2B / B2C / Moderation)

```
POST /api/v1/auth/login
Host: {service_url}
Content-Type: application/json
```

### Request

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

### Response 200 OK

```json
{
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

### Ошибки

| HTTP | code | Когда |
|------|------|-------|
| 400 | `INVALID_REQUEST` | Пустое тело / не email |
| 401 | `INVALID_CREDENTIALS` | Пара email+password не совпала (не раскрываем что именно не так) |
| 403 | `USER_BLOCKED` | Пользователь заблокирован |

**Важно**: код `INVALID_CREDENTIALS` — один и тот же, что для «нет такого email», что для «неверный пароль». Иначе утечка: атакующий может перебрать email-ы.

### Что делает сервис

1. Находит пользователя по `email`.
2. Проверяет хеш пароля.
3. Генерирует пару токенов.
4. Пишет `refresh.jti` в `refresh_tokens`.
5. Возвращает токены.

---

## 5. AUTH-4: Refresh токена

### Sequence (rotation + blacklist)

```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant API as Auth API
    participant DB as refresh_tokens + blacklist

    C->>API: POST /auth/refresh {refresh_token}
    API->>API: verify signature (RS256)
    API->>API: check exp (30 дней)

    alt signature invalid
        API-->>C: 401 INVALID_TOKEN
    else expired
        API-->>C: 401 TOKEN_EXPIRED
    else
        API->>DB: SELECT jti FROM refresh_blacklist WHERE jti = old_jti
        alt jti в blacklist (уже использован)
            DB-->>API: найден
            API-->>C: 401 TOKEN_REVOKED
            Note right of API: Сигнал: refresh украден.<br/>Все сессии этого user выкинуть,<br/>принудительная смена пароля.
        else
            API->>DB: SELECT FROM refresh_tokens WHERE jti = old_jti
            alt jti неизвестен
                API-->>C: 401 TOKEN_REVOKED
            else
                API->>API: generate new access + refresh (rotation)
                API->>DB: INSERT refresh_blacklist (old_jti)
                API->>DB: INSERT refresh_tokens (new_jti)
                API-->>C: 200 {access_token, refresh_token}
            end
        end
    end
```

### Endpoint

```
POST /api/v1/auth/refresh
Host: {service_url}
Content-Type: application/json
```

### Request

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Response 200 OK

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

Возвращается **новая пара** access + refresh. Старый refresh — уходит в blacklist (rotation).

### Ошибки

| HTTP | code | Когда |
|------|------|-------|
| 401 | `INVALID_TOKEN` | Невалидная подпись / формат |
| 401 | `TOKEN_EXPIRED` | Refresh истёк (30 дней прошло) |
| 401 | `TOKEN_REVOKED` | Refresh уже был использован (в blacklist) или logout сделан |

### Что делает сервис

1. Проверяет подпись refresh-токена.
2. Проверяет `exp` (не истёк).
3. Проверяет `jti` — нет ли в `refresh_blacklist` (если есть — `TOKEN_REVOKED`).
4. Проверяет `jti` в `refresh_tokens` (известен ли вообще такой токен) — если неизвестен, значит уже использовался или подделан -> `TOKEN_REVOKED`.
5. Генерирует новую пару.
6. **Добавляет старый `jti` в `refresh_blacklist`** (использованный refresh нельзя переиспользовать).
7. Пишет новый `jti` в `refresh_tokens`.
8. Возвращает новую пару.

**Почему rotation**: если атакующий украл refresh и использовал — легальный пользователь при следующем refresh получит `TOKEN_REVOKED` -> сигнал на выкидывание всех сессий и смену пароля.

---

## 6. AUTH-5: Logout

### Endpoint

```
POST /api/v1/auth/logout
Host: {service_url}
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Response 204 No Content

Тело пустое.

### Ошибки

| HTTP | code | Когда |
|------|------|-------|
| 401 | `INVALID_TOKEN` | Невалидный access_token |
| 400 | `INVALID_REQUEST` | Нет `refresh_token` в теле |

### Что делает сервис

1. Проверяет access_token (стандартный auth middleware).
2. Проверяет подпись refresh_token.
3. Проверяет, что `sub` в refresh совпадает с `sub` в access (иначе кто-то пытается разлогинить чужую сессию).
4. Пишет `refresh.jti` в `refresh_blacklist` с TTL до оригинального `exp`.
5. Возвращает `204`.

**Access-токен не blacklist-им** — его TTL всего 1 час, живём с этим. Если нужна жёсткая инвалидация — меняем `password` (выкидывает все сессии, т.к. refresh инвалидируются централизованно через `users.password_changed_at` > `iat`).

---

## 7. Таблицы БД (минимум для auth)

### 7.1. `users` (в каждом сервисе своя)

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID PK | = `sub` в JWT |
| `email` | varchar(255) UNIQUE | |
| `password_hash` | varchar(255) | argon2/bcrypt |
| `role` | varchar(20) | `seller` / `buyer` / `moderator` / `admin` |
| `is_active` | boolean | для блокировки |
| `created_at` | timestamptz | |
| `password_changed_at` | timestamptz | для инвалидации старых токенов |
| ... | ... | остальные поля по сервису (company_name, inn, first_name, ...) |

### 7.2. `refresh_tokens` (активные)

| Поле | Тип | Описание |
|------|-----|----------|
| `jti` | UUID PK | из claim `jti` |
| `user_id` | UUID FK -> users.id | |
| `issued_at` | timestamptz | = `iat` |
| `expires_at` | timestamptz | = `exp` |

Запись живёт до `expires_at`. Очистка — cron / management command раз в сутки.

### 7.3. `refresh_blacklist` (отозванные)

| Поле | Тип | Описание |
|------|-----|----------|
| `jti` | UUID PK | из claim `jti` отозванного токена |
| `revoked_at` | timestamptz | |
| `expires_at` | timestamptz | до этого момента держим, потом можно удалять |

Проверка при refresh: `SELECT 1 FROM refresh_blacklist WHERE jti = ?`.

---

## 8. Использование access_token на защищённых endpoint-ах

### 8.1. Заголовок

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 8.2. Извлечение seller_id / buyer_id / moderator_id

**Ключевое правило**: `seller_id`, `buyer_id`, `moderator_id` **никогда не приходят из тела запроса или query**. Они извлекаются из `sub` в JWT.

Пример (B2B, создание товара):

```python
# views.py
class ProductCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSeller]

    def post(self, request):
        # request.user.id = claims["sub"] (после auth middleware)
        product = Product.objects.create(
            seller_id=request.user.id,  # <-- из JWT, не из request.data
            name=request.data["name"],
            ...
        )
```

Это исключает IDOR: даже если атакующий пришлёт `"seller_id": "<чужой uuid>"` в теле — сервис его проигнорирует.

### 8.3. Проверка ownership (для mutation endpoint-ов)

```python
# для PATCH /api/v1/products/{product_id}
def patch(self, request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if product.seller_id != request.user.id:
        raise PermissionDenied(code="FORBIDDEN", message="Не ваш товар")
    # ...
```

Для каждого mutation endpoint, работающего с ресурсом seller-а / buyer-а — обязательная проверка ownership.

---

## 9. Ошибки аутентификации: сводная таблица

| HTTP | code | Когда |
|------|------|-------|
| 400 | `INVALID_REQUEST` | Невалидное тело запроса |
| 401 | `INVALID_TOKEN` | Невалидная подпись / формат токена |
| 401 | `TOKEN_EXPIRED` | Токен истёк (`exp` < now) |
| 401 | `TOKEN_REVOKED` | Refresh в blacklist (logout / rotation) |
| 401 | `INVALID_CREDENTIALS` | Неверная пара email+password при логине |
| 401 | `UNAUTHORIZED` | Нет заголовка Authorization на защищённом endpoint |
| 403 | `FORBIDDEN` | Роль не подходит (buyer на seller-endpoint) или нет ownership |
| 403 | `USER_BLOCKED` | Пользователь заблокирован |
| 409 | `EMAIL_ALREADY_EXISTS` | При регистрации |
| 409 | `INN_ALREADY_EXISTS` | При регистрации продавца |

Формат ошибки — стандартный `{"code": "...", "message": "..."}` (см. [type-unification.md](type-unification.md) §7).

---

## 10. Что за рамками этого документа

- **Восстановление пароля** (`POST /api/v1/auth/password/reset`) — отдельный flow, для следующей итерации.
- **Подтверждение email** — для учебного проекта можно пропустить, в проде нужно.
- **2FA** — out of scope.
- **OAuth/SSO** — out of scope.
- **Rate limiting на /login** — описывается в security guidelines.
- **CSRF для cookie-based auth** — если access_token в cookie, нужен CSRF-token. Для учебного проекта держим токен в Authorization header — CSRF не нужен.
