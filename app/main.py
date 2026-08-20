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
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import Response
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


class ReserveItem(BaseModel):
    sku_id: str
    quantity: int

    @field_validator("sku_id")
    @classmethod
    def sku_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("sku_id must be a valid UUID") from None
        return value

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be a positive integer")
        return value


class ReserveRequest(BaseModel):
    idempotency_key: str
    items: list[ReserveItem] = Field(min_length=1)

    @field_validator("idempotency_key")
    @classmethod
    def idempotency_key_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("idempotency_key must be a valid UUID") from None
        return value


class ReserveSuccessItem(BaseModel):
    sku_id: str
    reserved_quantity: int
    remaining_stock: int


class ReserveFailedItem(BaseModel):
    sku_id: str
    requested: int
    available: int
    reason: str


class ReserveResponse(BaseModel):
    reserved: bool
    items: list[ReserveSuccessItem] = Field(default_factory=list)
    failed_items: list[ReserveFailedItem] = Field(default_factory=list)


class UnreserveRequest(BaseModel):
    order_id: str
    items: list[ReserveItem] = Field(min_length=1)

    @field_validator("order_id")
    @classmethod
    def order_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("order_id must be a valid UUID") from None
        return value


class UnreserveResponse(BaseModel):
    ok: bool


class ModerationDecisionRequest(BaseModel):
    idempotency_key: str
    product_id: str
    status: str
    hard_block: bool = False
    blocking_reason: BlockingReason | None = None
    field_reports: list[FieldReport] = Field(default_factory=list)

    @field_validator("idempotency_key", "product_id")
    @classmethod
    def identifiers_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("identifier must be a valid UUID") from None
        return value

    @field_validator("status")
    @classmethod
    def status_must_be_supported(cls, value: str) -> str:
        if value not in {"MODERATED", "BLOCKED"}:
            raise ValueError("status must be MODERATED or BLOCKED")
        return value


class ModerationDecisionResponse(BaseModel):
    ok: bool


class UpdateProductRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=5000)


class DeleteResponse(BaseModel):
    deleted: bool


class CartAddRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sku_id: str
    quantity: int = Field(ge=1)

    @field_validator("sku_id")
    @classmethod
    def sku_id_must_be_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError):
            raise ValueError("sku_id must be a valid UUID") from None
        return value


class CartQuantityRequest(BaseModel):
    quantity: int = Field(ge=1)


class CartStoredItem(BaseModel):
    id: str
    sku_id: str
    quantity: int


class CartItemResponse(BaseModel):
    item_id: str
    sku_id: str
    quantity: int
    available: bool
    unavailable_reason: str | None = None
    available_stock: int
    unit_price: int
    line_total: int
    product_id: str
    product_title: str
    sku_name: str
    image_url: str | None = None


class CartSummary(BaseModel):
    total_amount: int
    total_items: int
    unavailable_count: int
    total_quantity: int = 0
    available_items: int = 0
    has_unavailable_items: bool = False
    checkout_ready: bool
    currency: str = "RUB"


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    summary: CartSummary
    checkout_payload: dict[str, Any]


class CartMutationResponse(BaseModel):
    message: str
    item: CartItemResponse
    summary: CartSummary


class CartValidationRequest(BaseModel):
    cart_item_ids: list[str] = Field(default_factory=list)


class CartValidationIssue(BaseModel):
    cart_item_id: str
    sku_id: str
    issue_type: str
    severity: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CartValidationResponse(BaseModel):
    is_valid: bool
    can_checkout: bool
    total_items: int
    validation_timestamp: str
    issues: list[CartValidationIssue]


class CartMergeResponse(BaseModel):
    merged: bool
    items: list[CartStoredItem]


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
    reserve_operations: dict[str, ReserveResponse] = field(default_factory=dict)
    unreserve_operations: dict[str, UnreserveResponse] = field(default_factory=dict)
    b2c_events: list[dict[str, Any]] = field(default_factory=list)
    processed_moderation_events: set[str] = field(default_factory=set)
    cart_items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _find_sku(self, sku_id: str) -> tuple[ProductResponse | None, SkuResponse | None]:
        for product in self.products.values():
            for sku in product.skus:
                if sku.id == sku_id:
                    return product, sku
        return None, None

    def _b2b_snapshot(self, sku_id: str) -> dict[str, Any] | None:
        """Fetch current product/SKU visibility from B2B for cart reads and writes."""
        base_url = os.getenv("B2B_URL") or os.getenv("B2B_SERVICE_URL")
        if not base_url:
            product, sku = self._find_sku(sku_id)
            if product is None or sku is None:
                return None
            return {"product_id": product.id, "product_title": product.title, "product_status": product.status, "product_deleted": product.deleted, "sku_name": sku.name, "image_url": sku.image, "unit_price": sku.price, "available_stock": sku.active_quantity}
        headers = {"X-Service-Key": os.getenv("B2C_TO_B2B_KEY", "development-service-key")}
        try:
            sku_response = httpx.get(f"{base_url.rstrip('/')}/api/v1/public/skus/{sku_id}", headers=headers, timeout=5.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=ApiError(code="B2B_UNAVAILABLE", message="B2B product service unavailable").model_dump()) from exc
        if sku_response.status_code == 404:
            return None
        if sku_response.status_code != 200:
            raise HTTPException(status_code=503, detail=ApiError(code="B2B_UNAVAILABLE", message="B2B product service unavailable").model_dump())
        sku_data = sku_response.json()
        product_id = sku_data.get("product_id")
        try:
            product_response = httpx.get(f"{base_url.rstrip('/')}/api/v1/public/products/{product_id}", headers=headers, timeout=5.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=ApiError(code="B2B_UNAVAILABLE", message="B2B product service unavailable").model_dump()) from exc
        if product_response.status_code == 404:
            return None
        if product_response.status_code != 200:
            raise HTTPException(status_code=503, detail=ApiError(code="B2B_UNAVAILABLE", message="B2B product service unavailable").model_dump())
        product_data = product_response.json()
        matched = next((item for item in product_data.get("skus", []) if item.get("id") == sku_id), sku_data)
        return {"product_id": product_data.get("id", product_id), "product_title": product_data.get("title"), "product_status": product_data.get("status"), "product_deleted": product_data.get("deleted", False), "sku_name": matched.get("name"), "image_url": matched.get("image"), "unit_price": matched.get("price", 0), "available_stock": matched.get("active_quantity", 0)}

    def add_cart_item(self, owner_type: str, owner_id: str, payload: CartAddRequest) -> tuple[dict[str, Any], bool]:
        snapshot = self._b2b_snapshot(payload.sku_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="SKU not found").model_dump())
        if snapshot["product_status"] != "MODERATED" or snapshot["product_deleted"]:
            raise HTTPException(status_code=409, detail=ApiError(code="SKU_UNAVAILABLE", message="SKU is unavailable").model_dump())
        if snapshot["available_stock"] < payload.quantity:
            raise HTTPException(status_code=409, detail=ApiError(code="OUT_OF_STOCK", message="Insufficient stock").model_dump())
        existing = next((item for item in self.cart_items.values() if item["owner_type"] == owner_type and item["owner_id"] == owner_id and item["sku_id"] == payload.sku_id), None)
        if existing:
            existing["quantity"] += payload.quantity
            return existing, False
        item = {"id": str(uuid.uuid4()), "owner_type": owner_type, "owner_id": owner_id, "sku_id": payload.sku_id, "quantity": payload.quantity}
        self.cart_items[item["id"]] = item
        return item, True

    def owned_cart_item(self, owner_type: str, owner_id: str, item_id: str) -> dict[str, Any]:
        item = self.cart_items.get(item_id)
        if item is None or item["owner_type"] != owner_type or item["owner_id"] != owner_id:
            raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="Cart item not found").model_dump())
        return item

    def cart_item_by_sku(self, owner_type: str, owner_id: str, sku_id: str) -> dict[str, Any]:
        item = next((candidate for candidate in self.list_cart(owner_type, owner_id) if candidate["sku_id"] == sku_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="Cart item not found").model_dump())
        return item

    def list_cart(self, owner_type: str, owner_id: str) -> list[dict[str, Any]]:
        return [item for item in self.cart_items.values() if item["owner_type"] == owner_type and item["owner_id"] == owner_id]

    def mutation_response(self, owner_type: str, owner_id: str, sku_id: str, message: str) -> CartMutationResponse:
        cart = self.enrich_cart(owner_type, owner_id)
        item = next((candidate for candidate in cart.items if candidate.sku_id == sku_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="Cart item not found").model_dump())
        return CartMutationResponse(message=message, item=item, summary=cart.summary)

    def validate_cart(self, owner_type: str, owner_id: str, requested_item_ids: list[str] | None = None) -> CartValidationResponse:
        selected_ids = set(requested_item_ids or [])
        stored_items = self.list_cart(owner_type, owner_id)
        if selected_ids:
            stored_items = [item for item in stored_items if item["id"] in selected_ids]
        issues: list[CartValidationIssue] = []
        for item in stored_items:
            snapshot = self._b2b_snapshot(item["sku_id"])
            issue_type: str | None = None
            message = ""
            details: dict[str, Any] = {"requested": item["quantity"]}
            if snapshot is None or snapshot.get("product_deleted"):
                issue_type = "DELETED"
                message = "SKU or product was deleted"
            elif snapshot.get("product_status") in {"BLOCKED", "HARD_BLOCKED"}:
                issue_type = "BLOCKED"
                message = "Product is blocked"
            elif snapshot.get("product_status") == "ON_MODERATION":
                issue_type = "ON_MODERATION"
                message = "Product is on moderation"
            elif snapshot.get("available_stock", 0) == 0:
                issue_type = "OUT_OF_STOCK"
                message = "SKU is out of stock"
            elif snapshot.get("available_stock", 0) < item["quantity"]:
                issue_type = "INSUFFICIENT_STOCK"
                message = "Insufficient stock"
                details["available"] = snapshot.get("available_stock", 0)
            if issue_type is not None:
                severity = "warning" if issue_type in {"INSUFFICIENT_STOCK", "ON_MODERATION"} else "critical"
                issues.append(CartValidationIssue(cart_item_id=item["id"], sku_id=item["sku_id"], issue_type=issue_type, severity=severity, message=message, details=details))
        total_items = len(stored_items)
        return CartValidationResponse(
            is_valid=not issues,
            can_checkout=total_items > 0 and not any(issue.severity == "critical" for issue in issues),
            total_items=total_items,
            validation_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            issues=issues,
        )

    def enrich_cart(self, owner_type: str, owner_id: str) -> CartResponse:
        enriched: list[CartItemResponse] = []
        total_amount = 0
        total_items = 0
        unavailable_count = 0
        checkout_items: list[dict[str, Any]] = []
        for item in self.list_cart(owner_type, owner_id):
            snapshot = self._b2b_snapshot(item["sku_id"])
            reason: str | None = None
            available = True
            product_id = snapshot.get("product_id") if snapshot and snapshot.get("product_id") else item["sku_id"]
            product_title = snapshot.get("product_title") if snapshot and snapshot.get("product_title") else "Unavailable product"
            image = snapshot.get("image_url") if snapshot else None
            unit_price = snapshot.get("unit_price", 0) if snapshot else 0
            available_stock = snapshot.get("available_stock", 0) if snapshot else 0
            product_status = snapshot.get("product_status") if snapshot else None
            product_deleted = snapshot.get("product_deleted", True) if snapshot else True
            if snapshot is None:
                available = False
                reason = "PRODUCT_DELETED"
            elif product_deleted or product_status == "DELETED":
                available = False
                reason = "PRODUCT_DELETED"
            elif product_status in {"BLOCKED", "HARD_BLOCKED"}:
                available = False
                reason = "PRODUCT_BLOCKED"
            elif product_status == "ON_MODERATION":
                available = False
                reason = "ON_MODERATION"
            elif available_stock == 0:
                available = False
                reason = "OUT_OF_STOCK"
            line_total = unit_price * item["quantity"] if available else 0
            if not available:
                unavailable_count += 1
            else:
                total_amount += line_total
                checkout_item = {"product_id": product_id, "sku_id": item["sku_id"], "quantity": item["quantity"], "unit_price": unit_price, "line_total": line_total}
                if available_stock < item["quantity"]:
                    checkout_items.append(checkout_item)
                else:
                    total_items += item["quantity"]
                    checkout_items.append(checkout_item)
            enriched.append(CartItemResponse(item_id=item["id"], sku_id=item["sku_id"], quantity=item["quantity"], available=available, unavailable_reason=reason, available_stock=available_stock, unit_price=unit_price, line_total=line_total, product_id=product_id, product_title=product_title,                 sku_name=snapshot.get("sku_name") if snapshot and snapshot.get("sku_name") else "Unavailable SKU", image_url=image))

        checkout_ready = unavailable_count == 0 and all(item.available_stock >= item.quantity for item in enriched)
        available_items = sum(1 for item in enriched if item.available)
        total_quantity = sum(item.quantity for item in enriched)
        return CartResponse(
            items=enriched,
            summary=CartSummary(total_amount=total_amount, total_items=len(enriched), unavailable_count=unavailable_count, total_quantity=total_quantity, available_items=available_items, has_unavailable_items=unavailable_count > 0, checkout_ready=checkout_ready),
            checkout_payload={"items": checkout_items, "total_amount": total_amount, "currency": "RUB"} if checkout_ready else {"items": [], "total_amount": 0, "currency": "RUB"},
        )

    def merge_guest_cart(self, session_id: str, user_id: str) -> CartMergeResponse:
        guest_items = [item for item in self.cart_items.values() if item["owner_type"] == "session" and item["owner_id"] == session_id]
        auth_items = {(item["sku_id"]): item for item in self.list_cart("user", user_id)}
        for guest in guest_items:
            existing = auth_items.get(guest["sku_id"])
            if existing:
                existing["quantity"] = max(existing["quantity"], guest["quantity"])
                self.cart_items.pop(guest["id"], None)
            else:
                guest["owner_type"] = "user"
                guest["owner_id"] = user_id
                auth_items[guest["sku_id"]] = guest
        items = [CartStoredItem(id=item["id"], sku_id=item["sku_id"], quantity=item["quantity"]) for item in self.list_cart("user", user_id)]
        return CartMergeResponse(merged=True, items=items)

    def apply_moderation(self, payload: ModerationDecisionRequest) -> ModerationDecisionResponse:
        if payload.idempotency_key in self.processed_moderation_events:
            return ModerationDecisionResponse(ok=True)
        product = self.products.get(payload.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump(),
            )

        if payload.status == "MODERATED":
            product.status = "MODERATED"
            product.blocked = False
            product.blocking_reason = None
            product.field_reports = []
        else:
            product.status = "HARD_BLOCKED" if payload.hard_block else "BLOCKED"
            product.blocked = True
            product.blocking_reason = payload.blocking_reason
            product.field_reports = payload.field_reports
            self.b2c_events.append(
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "event": "PRODUCT_BLOCKED",
                    "product_id": product.id,
                    "sku_ids": [sku.id for sku in product.skus],
                    "date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
        self.processed_moderation_events.add(payload.idempotency_key)
        return ModerationDecisionResponse(ok=True)

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

    def reserve(self, payload: ReserveRequest) -> ReserveResponse:
        cached = self.reserve_operations.get(payload.idempotency_key)
        if cached is not None:
            return cached

        sku_map: dict[str, SkuResponse] = {}
        failed: list[ReserveFailedItem] = []
        for item in payload.items:
            sku = next((candidate for product in self.products.values() for candidate in product.skus if candidate.id == item.sku_id), None)
            if sku is None:
                failed.append(ReserveFailedItem(sku_id=item.sku_id, requested=item.quantity, available=0, reason="OUT_OF_STOCK"))
            else:
                sku_map[item.sku_id] = sku
                if sku.active_quantity < item.quantity:
                    reason = "OUT_OF_STOCK" if sku.active_quantity == 0 else "INSUFFICIENT_STOCK"
                    failed.append(ReserveFailedItem(sku_id=item.sku_id, requested=item.quantity, available=sku.active_quantity, reason=reason))

        if failed:
            return ReserveResponse(reserved=False, failed_items=failed)

        result_items: list[ReserveSuccessItem] = []
        out_of_stock_ids: list[str] = []
        for item in payload.items:
            sku = sku_map[item.sku_id]
            sku.active_quantity -= item.quantity
            sku.reserved_quantity += item.quantity
            result_items.append(
                ReserveSuccessItem(
                    sku_id=sku.id,
                    reserved_quantity=item.quantity,
                    remaining_stock=sku.active_quantity,
                )
            )
            if sku.active_quantity == 0:
                out_of_stock_ids.append(sku.id)

        result = ReserveResponse(reserved=True, items=result_items)
        self.reserve_operations[payload.idempotency_key] = result
        for sku_id in out_of_stock_ids:
            self.b2c_events.append(
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "event": "SKU_OUT_OF_STOCK",
                    "sku_id": sku_id,
                    "date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
        return result

    def unreserve(self, payload: UnreserveRequest) -> UnreserveResponse:
        cached = self.unreserve_operations.get(payload.order_id)
        if cached is not None:
            return cached

        sku_map: dict[str, SkuResponse] = {}
        for item in payload.items:
            sku = next((candidate for product in self.products.values() for candidate in product.skus if candidate.id == item.sku_id), None)
            if sku is None or sku.reserved_quantity < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=ApiError(code="CONFLICT", message="Reserved quantity is insufficient").model_dump(),
                )
            sku_map[item.sku_id] = sku

        for item in payload.items:
            sku = sku_map[item.sku_id]
            sku.active_quantity += item.quantity
            sku.reserved_quantity -= item.quantity
        result = UnreserveResponse(ok=True)
        self.unreserve_operations[payload.order_id] = result
        return result

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


@app.post(
    "/api/v1/reserve",
    response_model=ReserveResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 409: {"model": ApiError}},
)
def reserve_skus(
    payload: ReserveRequest,
    x_service_key: Annotated[str | None, Header()] = None,
) -> ReserveResponse:
    if not _valid_b2c_service_key(x_service_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="UNAUTHORIZED", message="Valid X-Service-Key is required").model_dump(),
        )
    result = store.reserve(payload)
    if not result.reserved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.model_dump())
    return result


@app.post(
    "/api/v1/unreserve",
    response_model=UnreserveResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 409: {"model": ApiError}},
)
def unreserve_skus(
    payload: UnreserveRequest,
    x_service_key: Annotated[str | None, Header()] = None,
) -> UnreserveResponse:
    if not _valid_b2c_service_key(x_service_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="UNAUTHORIZED", message="Valid X-Service-Key is required").model_dump(),
        )
    return store.unreserve(payload)


def get_cart_identity(
    authorization: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> tuple[str, str]:
    if authorization:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail=ApiError(code="UNAUTHORIZED", message="Bearer token is required").model_dump())
        try:
            claims = _decode_jwt_payload(authorization[7:].strip())
            user_id = claims.get("sub") or claims.get("user_id")
            uuid.UUID(str(user_id))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
            raise HTTPException(status_code=401, detail=ApiError(code="UNAUTHORIZED", message="user_id claim is required").model_dump()) from None
        return "user", str(user_id)
    if not x_session_id:
        raise HTTPException(status_code=400, detail=ApiError(code="MISSING_CART_IDENTITY", message="JWT or X-Session-Id is required").model_dump())
    try:
        uuid.UUID(x_session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=ApiError(code="INVALID_REQUEST", message="X-Session-Id must be a valid UUID").model_dump()) from None
    return "session", x_session_id


@app.post(
    "/api/v1/cart/items",
    response_model=CartMutationResponse,
    status_code=status.HTTP_200_OK,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 409: {"model": ApiError}},
)
def add_cart_item(payload: CartAddRequest, identity: Annotated[tuple[str, str], Depends(get_cart_identity)]) -> CartMutationResponse:
    owner_type, owner_id = identity
    store.add_cart_item(owner_type, owner_id, payload)
    return store.mutation_response(owner_type, owner_id, payload.sku_id, "Cart item added successfully")


@app.get(
    "/api/v1/cart",
    response_model=CartResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 503: {"model": ApiError}},
)
def get_cart(identity: Annotated[tuple[str, str], Depends(get_cart_identity)]) -> CartResponse:
    return store.enrich_cart(*identity)


@app.put(
    "/api/v1/cart/items/{item_id}",
    response_model=CartMutationResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 404: {"model": ApiError}, 409: {"model": ApiError}},
)
def update_cart_item(item_id: str, payload: CartQuantityRequest, identity: Annotated[tuple[str, str], Depends(get_cart_identity)]) -> CartMutationResponse:
    owner_type, owner_id = identity
    item = store.owned_cart_item(owner_type, owner_id, item_id)
    snapshot = store._b2b_snapshot(item["sku_id"])
    if snapshot is None or snapshot["product_status"] != "MODERATED" or snapshot["product_deleted"]:
        raise HTTPException(status_code=410, detail=ApiError(code="PRODUCT_NOT_AVAILABLE", message="Product is unavailable").model_dump())
    if snapshot["available_stock"] < payload.quantity:
        raise HTTPException(status_code=422, detail=ApiError(code="INSUFFICIENT_STOCK", message="Insufficient stock").model_dump())
    item["quantity"] = payload.quantity
    return store.mutation_response(owner_type, owner_id, item["sku_id"], "Cart item quantity updated successfully")


@app.patch(
    "/api/v1/cart/items/{sku_id}",
    response_model=CartMutationResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 404: {"model": ApiError}, 409: {"model": ApiError}},
)
def patch_cart_item(sku_id: str, payload: CartQuantityRequest, identity: Annotated[tuple[str, str], Depends(get_cart_identity)]) -> CartMutationResponse:
    try:
        uuid.UUID(sku_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=ApiError(code="INVALID_REQUEST", message="sku_id must be a valid UUID").model_dump()) from None
    owner_type, owner_id = identity
    item = store.cart_item_by_sku(owner_type, owner_id, sku_id)
    snapshot = store._b2b_snapshot(sku_id)
    if snapshot is None or snapshot["product_status"] != "MODERATED" or snapshot["product_deleted"]:
        raise HTTPException(status_code=410, detail=ApiError(code="PRODUCT_NOT_AVAILABLE", message="Product is unavailable").model_dump())
    if snapshot["available_stock"] < payload.quantity:
        raise HTTPException(status_code=422, detail=ApiError(code="INSUFFICIENT_STOCK", message="Insufficient stock").model_dump())
    item["quantity"] = payload.quantity
    return store.mutation_response(owner_type, owner_id, sku_id, "Cart item quantity updated successfully")


@app.delete(
    "/api/v1/cart/items/{sku_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 404: {"model": ApiError}},
)
def delete_cart_item(sku_id: str, identity: Annotated[tuple[str, str], Depends(get_cart_identity)]) -> Response:
    try:
        uuid.UUID(sku_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=ApiError(code="INVALID_REQUEST", message="sku_id must be a valid UUID").model_dump()) from None
    item = store.cart_item_by_sku(*identity, sku_id)
    store.cart_items.pop(item["id"], None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/cart/validate",
    response_model=CartValidationResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 503: {"model": ApiError}},
)
def validate_cart_get(
    identity: Annotated[tuple[str, str], Depends(get_cart_identity)],
    cart_item_ids: list[str] | None = Query(default=None),
) -> CartValidationResponse:
    return store.validate_cart(*identity, cart_item_ids)


@app.post(
    "/api/v1/cart/validate",
    response_model=CartValidationResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 503: {"model": ApiError}},
)
def validate_cart(identity: Annotated[tuple[str, str], Depends(get_cart_identity)], payload: CartValidationRequest | None = None) -> CartValidationResponse:
    return store.validate_cart(*identity, payload.cart_item_ids if payload else None)


@app.delete(
    "/api/v1/cart",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}},
)
def clear_cart(identity: Annotated[tuple[str, str], Depends(get_cart_identity)]) -> Response:
    for item in store.list_cart(*identity):
        store.cart_items.pop(item["id"], None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/cart/merge",
    response_model=CartMergeResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}},
)
def merge_guest_cart(
    authorization: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> CartMergeResponse:
    if not x_session_id:
        raise HTTPException(status_code=400, detail=ApiError(code="MISSING_CART_IDENTITY", message="X-Session-Id is required for merge").model_dump())
    identity = get_cart_identity(authorization=authorization, x_session_id=None)
    if identity[0] != "user":
        raise HTTPException(status_code=401, detail=ApiError(code="UNAUTHORIZED", message="Bearer token is required for merge").model_dump())
    return store.merge_guest_cart(x_session_id, identity[1])


def _valid_moderation_service_key(value: str | None) -> bool:
    expected = os.getenv("MOD_TO_B2B_KEY", "development-service-key")
    return value is not None and value == expected


@app.post(
    "/api/v1/events/moderation",
    response_model=ModerationDecisionResponse,
    responses={400: {"model": ApiError}, 401: {"model": ApiError}, 404: {"model": ApiError}},
)
def apply_moderation_event(
    payload: ModerationDecisionRequest,
    x_service_key: Annotated[str | None, Header()] = None,
) -> ModerationDecisionResponse:
    if not _valid_moderation_service_key(x_service_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ApiError(code="UNAUTHORIZED", message="Valid X-Service-Key is required").model_dump(),
        )
    return store.apply_moderation(payload)


@app.put(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}},
)
def update_product(
    product_id: str,
    payload: UpdateProductRequest,
    seller_id: Annotated[str, Depends(get_seller_id)],
) -> ProductResponse:
    product = store.products.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump())
    if product.seller_id != seller_id:
        raise HTTPException(status_code=403, detail=ApiError(code="NOT_OWNER", message="Product does not belong to the authenticated seller").model_dump())
    if product.status == "HARD_BLOCKED":
        raise HTTPException(status_code=403, detail=ApiError(code="FORBIDDEN", message="Cannot edit hard-blocked product").model_dump())
    if payload.title is not None:
        product.title = payload.title
    if payload.description is not None:
        product.description = payload.description
    if product.status in {"MODERATED", "BLOCKED"}:
        product.status = "ON_MODERATION"
        product.blocked = False
    return product


@app.delete(
    "/api/v1/products/{product_id}",
    response_model=DeleteResponse,
    responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}},
)
def delete_product(
    product_id: str,
    seller_id: Annotated[str, Depends(get_seller_id)],
) -> DeleteResponse:
    product = store.products.get(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=ApiError(code="NOT_FOUND", message="Product not found").model_dump())
    if product.seller_id != seller_id:
        raise HTTPException(status_code=403, detail=ApiError(code="NOT_OWNER", message="Product does not belong to the authenticated seller").model_dump())
    if product.status == "HARD_BLOCKED":
        raise HTTPException(status_code=403, detail=ApiError(code="FORBIDDEN", message="Cannot delete hard-blocked product").model_dump())
    product.deleted = True
    product.status = "DELETED"
    return DeleteResponse(deleted=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
