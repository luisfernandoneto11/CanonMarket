"""NeoMarket B2B API: product and SKU creation flows."""

from __future__ import annotations

import base64
import binascii
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, Callable

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


app = FastAPI(title="NeoMarket B2B", version="1.0.0")

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
    # Ignore an untrusted body seller_id; ownership always comes from JWT.
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category_id: str
    images: list[Image] = Field(min_length=1)
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
    cost_price: int
    discount: int = 0
    image: str = Field(min_length=1)
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
    def price_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("price must be a positive integer (kopecks)")
        return value

    @field_validator("cost_price")
    @classmethod
    def cost_price_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("cost_price must be a positive integer (kopecks)")
        return value

    @field_validator("discount")
    @classmethod
    def discount_must_not_be_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("discount must be a non-negative integer (kopecks)")
        return value


class CategoryRef(BaseModel):
    id: str
    name: str


class SkuResponse(BaseModel):
    id: str
    product_id: str
    name: str
    price: int
    cost_price: int
    discount: int
    image: str
    active_quantity: int = 0
    reserved_quantity: int = 0
    characteristics: list[Characteristic]


class BlockingReason(BaseModel):
    id: str
    title: str
    comment: str


class FieldReport(BaseModel):
    field_name: str
    sku_id: str | None = None
    comment: str


class ProductResponse(BaseModel):
    id: str
    seller_id: str
    title: str
    description: str
    status: str
    deleted: bool
    blocked: bool
    category: CategoryRef
    images: list[Image]
    characteristics: list[Characteristic]
    skus: list[SkuResponse]
    blocking_reason: BlockingReason | None = None
    field_reports: list[FieldReport] = Field(default_factory=list)



class PublicSkuResponse(BaseModel):
    id: str
    product_id: str
    name: str
    price: int
    discount: int
    image: str
    active_quantity: int
    characteristics: list[Characteristic]


class CatalogProductResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    category: CategoryRef
    images: list[Image]
    characteristics: list[Characteristic]
    skus: list[PublicSkuResponse]


class CatalogResponse(BaseModel):
    items: list[CatalogProductResponse]
    total_count: int
    limit: int
    offset: int


class ModerationEvent(BaseModel):
    idempotency_key: str
    product_id: str
    seller_id: str
    event: str
    date: str


class ModerationPublisher:
    """Publishes synchronously when MODERATION_URL is configured and always records events."""

    def __init__(self, url: str | None = None, service_key: str | None = None):
        self.url = url or os.getenv("MODERATION_URL")
        self.service_key = service_key or os.getenv("B2B_TO_MOD_KEY", "development-service-key")
        self.events: list[ModerationEvent] = []

    def publish_created(self, product: ProductResponse) -> ModerationEvent:
        event = ModerationEvent(
            idempotency_key=str(uuid.uuid4()),
            product_id=product.id,
            seller_id=product.seller_id,
            event="CREATED",
            date=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        self.events.append(event)
        if self.url:
            response = httpx.post(
                f"{self.url.rstrip('/')}/api/v1/events/product",
                headers={"X-Service-Key": self.service_key},
                json=event.model_dump(),
                timeout=5.0,
            )
            response.raise_for_status()
        return event


@dataclass
class ProductStore:
    products: dict[str, ProductResponse] = field(default_factory=dict)
    moderation: ModerationPublisher = field(default_factory=ModerationPublisher)

    def create(self, payload: CreateProductRequest, seller_id: str) -> ProductResponse:
        product_id = str(uuid.uuid4())
        product = ProductResponse(
            id=product_id,
            seller_id=seller_id,
            title=payload.title,
            description=payload.description,
            status="CREATED",
            deleted=False,
            blocked=False,
            category=CategoryRef(
                id=payload.category_id,
                name=CATEGORY_NAMES.get(payload.category_id, "Category"),
            ),
            images=payload.images,
            characteristics=payload.characteristics,
            skus=[],
            blocking_reason=None,
            field_reports=[],
        )
        self.products[product_id] = product
        return product

    def add_sku(self, payload: CreateSkuRequest) -> tuple[SkuResponse, bool]:
        product = self.products.get(payload.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump(),
            )
        if product.status == "HARD_BLOCKED" or product.blocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ApiError(
                    code="FORBIDDEN",
                    message="Cannot add SKU to hard-blocked product",
                ).model_dump(),
            )

        sku = SkuResponse(
            id=str(uuid.uuid4()),
            product_id=product.id,
            name=payload.name,
            price=payload.price,
            cost_price=payload.cost_price,
            discount=payload.discount,
            image=payload.image,
            characteristics=payload.characteristics,
        )
        is_first_sku = len(product.skus) == 0
        product.skus.append(sku)
        if is_first_sku and product.status == "CREATED":
            product.status = "ON_MODERATION"
            self.moderation.publish_created(product)
        return sku, is_first_sku


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


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc: RequestValidationError):
    errors = exc.errors()
    if not errors:
        message = "Invalid request"
    else:
        error = errors[0]
        field = str(error.get("loc", ["request"])[-1])
        raw_message = str(error.get("msg", "is required")).replace("Value error, ", "")
        canonical = {
            "images": "At least one image is required",
            "image": "image is required",
            "name": "name is required",
            "price": "price must be a positive integer (kopecks)",
            "cost_price": "cost_price must be a positive integer (kopecks)",
            "product_id": "product_id must be a valid UUID",
            "category_id": "category_id must be a valid UUID",
        }
        message = canonical.get(field, raw_message)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ApiError(code="INVALID_REQUEST", message=message).model_dump(),
    )


def _valid_b2c_service_key(value: str | None) -> bool:
    expected = os.getenv("B2C_TO_B2B_KEY", "development-service-key")
    return value is not None and value == expected


def _to_catalog_product(product: ProductResponse) -> CatalogProductResponse:
    return CatalogProductResponse(
        id=product.id,
        title=product.title,
        description=product.description,
        status=product.status,
        category=product.category,
        images=product.images,
        characteristics=product.characteristics,
        skus=[
            PublicSkuResponse(
                id=sku.id,
                product_id=sku.product_id,
                name=sku.name,
                price=sku.price,
                discount=sku.discount,
                image=sku.image,
                active_quantity=sku.active_quantity,
                characteristics=sku.characteristics,
            )
            for sku in product.skus
            if sku.active_quantity > 0
        ],
    )


@app.get(
    "/api/v1/products",
    response_model=CatalogResponse,
    responses={401: {"model": ApiError}},
)
def list_catalog_products(
    limit: int = 20,
    offset: int = 0,
    category: str | None = None,
    search: str | None = None,
    sort: str = "date_desc",
    ids: str | None = None,
    x_service_key: Annotated[str | None, Header()] = None,
) -> CatalogResponse:
    """Return only visible, in-stock MODERATED products for B2C."""
    if not _valid_b2c_service_key(x_service_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="UNAUTHORIZED", message="Valid X-Service-Key is required").model_dump(),
        )
    if limit < 1 or limit > 100 or offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ApiError(code="INVALID_REQUEST", message="limit must be 1-100 and offset must be non-negative").model_dump(),
        )
    if sort not in {"price_asc", "price_desc", "date_desc"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ApiError(code="INVALID_REQUEST", message="Unsupported sort value").model_dump(),
        )

    requested_ids = None
    if ids:
        requested_ids = {item.strip() for item in ids.split(",") if item.strip()}
    normalized_search = search.casefold() if search else None
    visible: list[ProductResponse] = []
    for product in store.products.values():
        if requested_ids is not None and product.id not in requested_ids:
            continue
        if product.status != "MODERATED" or product.deleted:
            continue
        if category and product.category.id != category:
            continue
        if normalized_search and normalized_search not in f"{product.title} {product.description}".casefold():
            continue
        if not any(sku.active_quantity > 0 for sku in product.skus):
            continue
        visible.append(product)

    if sort == "price_asc":
        visible.sort(key=lambda product: min(sku.price for sku in product.skus if sku.active_quantity > 0))
    elif sort == "price_desc":
        visible.sort(key=lambda product: min(sku.price for sku in product.skus if sku.active_quantity > 0), reverse=True)

    total_count = len(visible)
    page = visible[offset : offset + limit]
    return CatalogResponse(
        items=[_to_catalog_product(product) for product in page],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


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
    responses={400: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}},
)
def create_sku(
    payload: CreateSkuRequest,
    seller_id: Annotated[str, Depends(get_seller_id)],
) -> SkuResponse:
    product = store.products.get(payload.product_id)
    if product is not None and product.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ApiError(code="NOT_OWNER", message="Product does not belong to the authenticated seller").model_dump(),
        )
    sku, _ = store.add_sku(payload)
    return sku


@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    responses={401: {"model": ApiError}, 404: {"model": ApiError}},
)
def get_product(
    product_id: str,
    authorization: Annotated[str | None, Header()] = None,
    x_service_key: Annotated[str | None, Header()] = None,
) -> ProductResponse:
    """Return a seller-owned product or a Moderation-authorized product.

    Seller access deliberately returns 404 for another seller's product to avoid
    revealing whether the resource exists. Moderation may use X-Service-Key to
    inspect any seller's product while building a moderation diff.
    """
    try:
        uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump(),
        ) from None

    product = store.products.get(product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump(),
        )

    expected_service_key = os.getenv("B2B_TO_MOD_KEY", "development-service-key")
    if x_service_key is not None:
        if x_service_key != expected_service_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ApiError(code="UNAUTHORIZED", message="Invalid service key").model_dump(),
            )
        return product

    seller_id = get_seller_id(authorization)
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump(),
        )
    return product


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
