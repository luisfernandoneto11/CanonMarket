import base64
import json

from fastapi.testclient import TestClient

from app.main import app, store


client = TestClient(app)
SELLER_ID = "c3d4e5f6-a7b8-9012-cdef-123456789012"
OTHER_SELLER_ID = "d4e5f6a7-b8c9-0123-def4-234567890123"
CATEGORY_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"


def jwt_for(seller_id: str = SELLER_ID) -> str:
    def part(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part({'seller_id': seller_id})}.signature"


def product_payload() -> dict:
    return {
        "title": "iPhone 15 Pro Max",
        "description": "Flagship smartphone",
        "category_id": CATEGORY_ID,
        "images": [{"url": "/s3/iphone15-front.jpg", "ordering": 0}],
        "characteristics": [{"name": "Brand", "value": "Apple"}],
    }


def sku_payload(product_id: str) -> dict:
    return {
        "product_id": product_id,
        "name": "256GB Black",
        "price": 12999000,
        "cost_price": 9500000,
        "discount": 0,
        "image": "/s3/iphone15-black-256.jpg",
        "characteristics": [{"name": "Color", "value": "Black"}],
    }


def create_product(status: str | None = None, seller_id: str = SELLER_ID) -> str:
    response = client.post(
        "/api/v1/products", json=product_payload(), headers={"Authorization": f"Bearer {jwt_for(seller_id)}"}
    )
    assert response.status_code == 201
    product_id = response.json()["id"]
    if status is not None:
        store.products[product_id].status = status
    return product_id


def setup_function():
    store.products.clear()
    store.moderation.events.clear()


def test_create_product_returns_201_with_created_status():
    response = client.post(
        "/api/v1/products", json=product_payload(), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "CREATED"
    assert body["skus"] == []
    assert body["deleted"] is False
    assert body["blocked"] is False


def test_seller_id_taken_from_jwt():
    payload = product_payload()
    payload["seller_id"] = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert response.json()["seller_id"] == SELLER_ID


def test_missing_images_returns_400():
    payload = product_payload()
    del payload["images"]

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "At least one image is required",
    }


def test_missing_category_returns_400():
    payload = product_payload()
    del payload["category_id"]

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert "category_id" in response.json()["message"]


def test_invalid_category_id_returns_400():
    payload = product_payload()
    payload["category_id"] = "not-a-uuid"

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "category_id must be a valid UUID",
    }


def test_unknown_category_returns_400():
    payload = product_payload()
    payload["category_id"] = "00000000-0000-0000-0000-000000000001"

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 400
    assert response.json() == {"code": "INVALID_REQUEST", "message": "Category not found"}


def test_first_sku_transitions_product_to_on_moderation():
    product_id = create_product()

    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert store.products[product_id].status == "ON_MODERATION"
    assert len(store.products[product_id].skus) == 1


def test_first_sku_emits_created_event_to_moderation():
    product_id = create_product()

    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert len(store.moderation.events) == 1
    event = store.moderation.events[0]
    assert event.product_id == product_id
    assert event.seller_id == SELLER_ID
    assert event.event == "CREATED"
    assert event.idempotency_key
    assert event.date.endswith("Z")


def test_second_sku_no_state_change():
    product_id = create_product()
    headers = {"Authorization": f"Bearer {jwt_for()}"}
    first = client.post("/api/v1/skus", json=sku_payload(product_id), headers=headers)
    assert first.status_code == 201
    events_after_first = len(store.moderation.events)
    status_after_first = store.products[product_id].status

    second_payload = sku_payload(product_id)
    second_payload["name"] = "512GB White"
    second = client.post("/api/v1/skus", json=second_payload, headers=headers)

    assert second.status_code == 201
    assert store.products[product_id].status == status_after_first
    assert len(store.moderation.events) == events_after_first
    assert len(store.products[product_id].skus) == 2


def test_add_sku_to_hard_blocked_returns_403():
    product_id = create_product(status="HARD_BLOCKED")

    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "Cannot add SKU to hard-blocked product",
    }


def test_missing_image_returns_400():
    product_id = create_product()
    payload = sku_payload(product_id)
    del payload["image"]

    response = client.post(
        "/api/v1/skus", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 400
    assert response.json() == {"code": "INVALID_REQUEST", "message": "image is required"}


def test_sku_product_not_found_returns_404():
    payload = sku_payload("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    response = client.post(
        "/api/v1/skus", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Product not found"}


def test_sku_owner_is_taken_from_jwt():
    product_id = create_product(seller_id=OTHER_SELLER_ID)

    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_OWNER"
