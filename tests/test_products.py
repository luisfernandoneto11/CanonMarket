import base64
import json

from fastapi.testclient import TestClient

from app.main import app, store


client = TestClient(app)
SELLER_ID = "c3d4e5f6-a7b8-9012-cdef-123456789012"
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


def setup_function():
    store.products.clear()
    store.moderation_events.clear()


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
    assert body["category_id"] == CATEGORY_ID
    assert body["slug"] == "iphone-15-pro-max"
    assert body["blocking_reason_id"] is None
    assert body["moderator_comment"] is None
    assert body["created_at"].endswith("Z")
    assert body["updated_at"].endswith("Z")


def test_seller_id_taken_from_jwt():
    payload = product_payload()
    payload["seller_id"] = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert response.json()["seller_id"] == SELLER_ID


def test_missing_images_defaults_to_empty_list():
    payload = product_payload()
    del payload["images"]

    response = client.post(
        "/api/v1/products", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["images"] == []
    assert body["status"] == "CREATED"


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



def sku_payload(product_id: str, name: str = "256GB Black") -> dict:
    return {
        "product_id": product_id,
        "name": name,
        "price": 12999000,
        "cost_price": 9000000,
        "discount": 0,
        "article": "IPH15-BLK-256",
        "images": [{"url": "/s3/iphone15-sku.jpg", "ordering": 0}],
        "characteristics": [{"name": "Storage", "value": "256GB"}],
    }


def create_product_for_sku(status_value: str = "CREATED") -> str:
    response = client.post(
        "/api/v1/products", json=product_payload(), headers={"Authorization": f"Bearer {jwt_for()}"}
    )
    assert response.status_code == 201
    product_id = response.json()["id"]
    store.products[product_id].status = status_value
    store.products[product_id].blocked = status_value == "BLOCKED"
    return product_id


def test_create_sku_returns_complete_contract_response():
    product_id = create_product_for_sku()
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["product_id"] == product_id
    assert body["name"] == "256GB Black"
    assert body["price"] == 12999000
    assert body["discount"] == 0
    assert body["cost_price"] == 9000000
    assert body["active_quantity"] == 0
    assert body["reserved_quantity"] == 0
    assert body["article"] == "IPH15-BLK-256"
    assert body["images"] == [{"url": "/s3/iphone15-sku.jpg", "ordering": 0}]
    assert body["characteristics"] == [{"name": "Storage", "value": "256GB"}]


def test_first_sku_transitions_product_and_emits_product_created_event():
    product_id = create_product_for_sku()
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert store.products[product_id].status == "ON_MODERATION"
    assert len(store.moderation_events) == 1
    event = store.moderation_events[0]
    assert event.event_type == "PRODUCT_CREATED"
    assert event.product_id == product_id
    assert event.seller_id == SELLER_ID
    assert event.json_after["id"] == product_id


def test_second_sku_does_not_change_status_or_emit_event():
    product_id = create_product_for_sku()
    headers = {"Authorization": f"Bearer {jwt_for()}"}
    assert client.post("/api/v1/skus", json=sku_payload(product_id), headers=headers).status_code == 201
    assert len(store.moderation_events) == 1
    store.products[product_id].status = "ON_MODERATION"

    response = client.post("/api/v1/skus", json=sku_payload(product_id, "512GB White"), headers=headers)

    assert response.status_code == 201
    assert store.products[product_id].status == "ON_MODERATION"
    assert len(store.moderation_events) == 1


def test_sku_on_moderated_product_restarts_moderation_with_edit_event():
    product_id = create_product_for_sku("MODERATED")
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert store.products[product_id].status == "ON_MODERATION"
    assert store.moderation_events[-1].event_type == "PRODUCT_EDITED"


def test_sku_on_blocked_product_restarts_moderation_with_edit_event():
    product_id = create_product_for_sku("BLOCKED")
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 201
    assert store.products[product_id].status == "ON_MODERATION"
    assert store.moderation_events[-1].event_type == "PRODUCT_EDITED"


def test_add_sku_to_hard_blocked_returns_403():
    product_id = create_product_for_sku("HARD_BLOCKED")
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )
    assert response.status_code == 403


def test_add_sku_to_another_seller_product_returns_403():
    product_id = create_product_for_sku()
    other_seller = "d4e5f6a7-b8c9-0123-def0-234567890123"
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for(other_seller)}"}
    )
    assert response.status_code == 403


def test_add_sku_requires_name_and_uses_integer_price():
    product_id = create_product_for_sku()
    payload = sku_payload(product_id)
    del payload["name"]
    payload["price"] = 12999000.5
    response = client.post(
        "/api/v1/skus", json=payload, headers={"Authorization": f"Bearer {jwt_for()}"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
