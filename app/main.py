"""NeoMarket B2B API: product creation flow."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


app = FastAPI(title="NeoMarket B2B", version="1.0.0")

# The canon currently publishes this category in the create-product example.
# Deployments can add comma-separated UUIDs through VALID_CATEGORY_IDS.
_CANON_CATEGORY_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
VALID_CATEGORY_IDS = {
    _CANON_CATEGORY_ID,
    *filter(None, os.getenv("VALID_CATEGORY_IDS", "").split(",")),
}
CATEGORY_NAMES = {_CANON_CATEGORY_ID: "iOS"}


class ApiError(BaseModel):
    code: str
    message: str


class Image(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    ordering: int = Field(ge=0)


class Characteristic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)


class CreateProductRequest(BaseModel):
    # Unknown fields are ignored so a body-provided seller_id cannot override JWT ownership.
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category_id: str
    images: list[Image] = Field(default_factory=list)
    characteristics: list[Characteristic] = Field(default_factory=list)

    @field_validator("category_id")
    @classmethod
    def category_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("category_id must be a valid UUID") from None
        return value


class CreateSkuRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    name: str = Field(min_length=1, max_length=255)
    price: int
    cost_price: int = 0
    discount: int = 0
    article: str | None = Field(default=None, max_length=100)
    images: list[Image] = Field(default_factory=list)
    characteristics: list[Characteristic] = Field(default_factory=list)

    @field_validator("product_id")
    @classmethod
    def product_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("product_id must be a valid UUID") from None
        return value

    @field_validator("price")
    @classmethod
    def price_must_be_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("price must be a positive integer (kopecks)")
        return value

    @field_validator("cost_price", "discount")
    @classmethod
    def money_fields_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("money fields must be non-negative integers (kopecks)")
        return value


class SkuResponse(BaseModel):
    id: str
    product_id: str
    name: str
    price: int
    discount: int
    cost_price: int
    active_quantity: int
    reserved_quantity: int
    article: str
    images: list[Image]
    characteristics: list[Characteristic]
    created_at: str
    updated_at: str


class ModerationEvent(BaseModel):
    idempotency_key: str
    product_id: str
    seller_id: str
    event_type: str
    json_after: dict[str, Any]
    date: str


class CategoryRef(BaseModel):
    id: str
    name: str


class ProductResponse(BaseModel):
    id: str
    seller_id: str
    title: str
    description: str
    status: str
    deleted: bool
    blocked: bool
    category_id: str
    category: CategoryRef
    slug: str
    images: list[Image]
    characteristics: list[Characteristic]
    skus: list[Any]
    blocking_reason_id: str | None = None
    moderator_comment: str | None = None
    created_at: str
    updated_at: str


@dataclass
class ProductStore:
    products: dict[str, ProductResponse] = field(default_factory=dict)
    moderation_events: list[ModerationEvent] = field(default_factory=list)

    def _publish_sku_event(self, product: ProductResponse, event_type: str, sku: SkuResponse) -> ModerationEvent:
        event = ModerationEvent(
            idempotency_key=str(uuid.uuid4()),
            product_id=product.id,
            seller_id=product.seller_id,
            event_type=event_type,
            json_after=product.model_dump(mode="json"),
            date=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self.moderation_events.append(event)
        moderation_url = os.getenv("MODERATION_URL")
        if moderation_url:
            response = httpx.post(
                f"{moderation_url.rstrip('/')}/api/v1/events/product",
                headers={"X-Service-Key": os.getenv("B2B_TO_MOD_KEY", "development-service-key")},
                json=event.model_dump(mode="json"),
                timeout=5.0,
            )
            if response.status_code not in {200, 202}:
                raise HTTPException(status_code=502, detail=ApiError(code="MODERATION_UNAVAILABLE", message="Moderation service rejected product event").model_dump())
        return event

    def create(self, payload: CreateProductRequest, seller_id: str) -> ProductResponse:
        product_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        slug = re.sub(r"[^a-z0-9]+", "-", payload.title.lower()).strip("-") or product_id
        product = ProductResponse(
            id=product_id,
            seller_id=seller_id,
            title=payload.title,
            description=payload.description,
            status="CREATED",
            deleted=False,
            blocked=False,
            category_id=payload.category_id,
            category=CategoryRef(
                id=payload.category_id,
                name=CATEGORY_NAMES.get(payload.category_id, "Category"),
            ),
            images=payload.images,
            characteristics=payload.characteristics,
            skus=[],
            slug=slug,
            blocking_reason_id=None,
            moderator_comment=None,
            created_at=now,
            updated_at=now,
        )
        self.products[product_id] = product
        return product

    def add_sku(self, payload: CreateSkuRequest, seller_id: str) -> tuple[SkuResponse, bool]:
        product = self.products.get(payload.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump())
        if product.seller_id != seller_id:
            raise HTTPException(status_code=403, detail=ApiError(code="NOT_OWNER", message="Product does not belong to the authenticated seller").model_dump())
        if product.status == "HARD_BLOCKED":
            raise HTTPException(status_code=403, detail=ApiError(code="FORBIDDEN", message="Cannot add SKU to hard-blocked product").model_dump())
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        sku_id = str(uuid.uuid4())
        sku = SkuResponse(
            id=sku_id,
            product_id=product.id,
            name=payload.name,
            price=payload.price,
            discount=payload.discount,
            cost_price=payload.cost_price,
            active_quantity=0,
            reserved_quantity=0,
            article=payload.article or f"SKU-{sku_id[:8]}",
            images=payload.images,
            characteristics=payload.characteristics,
            created_at=now,
            updated_at=now,
        )
        is_first = len(product.skus) == 0
        product.skus.append(sku)
        if is_first and product.status == "CREATED":
            product.status = "ON_MODERATION"
            self._publish_sku_event(product, "PRODUCT_CREATED", sku)
        elif product.status in {"MODERATED", "BLOCKED"}:
            product.status = "ON_MODERATION"
            product.blocked = False
            self._publish_sku_event(product, "PRODUCT_EDITED", sku)
        return sku, is_first


store = ProductStore()


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode claims for the service boundary; signature verification belongs to auth gateway."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT")
    encoded = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid JWT claims")
    return payload


def get_seller_id(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="UNAUTHORIZED", message="Bearer token is required").model_dump(),
        )
    try:
        claims = _decode_jwt_payload(authorization[7:].strip())
        seller_id = claims.get("seller_id")
        uuid.UUID(str(seller_id))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="UNAUTHORIZED", message="seller_id claim is required").model_dump(),
        ) from None
    return str(seller_id)


def validation_error_response(exc: Exception) -> HTTPException:
    message = str(exc)
    if "category_id must be a valid UUID" in message:
        message = "category_id must be a valid UUID"
    elif "images" in message:
        message = "At least one image is required"
    elif "title" in message:
        message = "title must be 1-255 characters"
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ApiError(code="INVALID_REQUEST", message=message).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    # Keep the public error contract stable while preserving FastAPI's status codes.
    from fastapi.responses import JSONResponse

    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.post(
    "/api/v1/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}},
)
def create_product(
    payload: CreateProductRequest,
    seller_id: Annotated[str, Depends(get_seller_id)],
) -> ProductResponse:
    if payload.category_id not in VALID_CATEGORY_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ApiError(code="INVALID_REQUEST", message="Category not found").model_dump(),
        )
    return store.create(payload, seller_id)


@app.post(
    "/api/v1/skus",
    response_model=SkuResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}},
)
def create_sku(
    payload: CreateSkuRequest,
    seller_id: Annotated[str, Depends(get_seller_id)],
) -> SkuResponse:
    sku, _ = store.add_sku(payload, seller_id)
    return sku


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Pydantic validation errors are normalized to the canon's error envelope.
from fastapi.exceptions import RequestValidationError


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc: RequestValidationError):
    from fastapi.responses import JSONResponse

    errors = exc.errors()
    field = str(errors[0].get("loc", ["request"])[-1]) if errors else "request"
    message_map = {
        "images": "At least one image is required",
        "category_id": "category_id must be a valid UUID",
        "title": "title must be 1-255 characters",
    }
    message = message_map.get(field, f"{field} is required")
    return JSONResponse(
        status_code=400,
        content=ApiError(code="INVALID_REQUEST", message=message).model_dump(),
    )
