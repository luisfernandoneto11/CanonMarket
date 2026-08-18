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
