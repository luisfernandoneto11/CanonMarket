import base64
import json

from fastapi.testclient import TestClient

from app.main import BlockingReason, FieldReport, app, store


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
    store.reserve_operations.clear()
    store.unreserve_operations.clear()
    store.b2c_events.clear()
    store.processed_moderation_events.clear()


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


def test_get_moderated_product_returns_full_payload():
    product_id = create_product()
    product = store.products[product_id]
    product.status = "MODERATED"
    sku_response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )
    assert sku_response.status_code == 201
    product.status = "MODERATED"

    response = client.get(
        f"/api/v1/products/{product_id}", headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "MODERATED"
    assert body["title"] == "iPhone 15 Pro Max"
    assert body["description"] == "Flagship smartphone"
    assert body["skus"][0]["cost_price"] == 9500000
    assert body["skus"][0]["reserved_quantity"] == 0
    assert body["blocking_reason"] is None
    assert body["field_reports"] == []


def test_get_blocked_product_returns_blocking_reason_and_field_reports():
    product_id = create_product()
    product = store.products[product_id]
    product.status = "BLOCKED"
    product.blocked = True
    product.blocking_reason = BlockingReason(
        id="a7b8c9d0-1234-5678-ef01-890123456789",
        title="Description does not match product",
        comment="Description and photos do not match",
    )
    product.field_reports = [
        FieldReport(
            field_name="description",
            sku_id=None,
            comment="Correct the material description",
        )
    ]

    response = client.get(
        f"/api/v1/products/{product_id}", headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert body["blocked"] is True
    assert body["blocking_reason"]["title"] == "Description does not match product"
    assert body["field_reports"][0]["field_name"] == "description"
    assert body["field_reports"][0]["sku_id"] is None


def test_get_others_product_returns_404():
    product_id = create_product(seller_id=OTHER_SELLER_ID)

    response = client.get(
        f"/api/v1/products/{product_id}", headers={"Authorization": f"Bearer {jwt_for()}"}
    )

    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Product not found"}


def test_get_nonexistent_returns_404():
    response = client.get(
        "/api/v1/products/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        headers={"Authorization": f"Bearer {jwt_for()}"},
    )

    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Product not found"}


def make_moderated_product(active_quantity: int = 5, title: str = "Visible phone") -> str:
    product_id = create_product()
    product = store.products[product_id]
    product.title = title
    product.status = "MODERATED"
    sku_result = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )
    assert sku_result.status_code == 201
    product.status = "MODERATED"
    product.skus[0].active_quantity = active_quantity
    return product_id


def test_catalog_returns_moderated_in_stock_products():
    visible_id = make_moderated_product(active_quantity=5)
    make_moderated_product(active_quantity=0, title="Out of stock")
    create_product(status="BLOCKED")

    response = client.get("/api/v1/products", headers={"X-Service-Key": "development-service-key"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["id"] == visible_id
    assert body["items"][0]["status"] == "MODERATED"


def test_catalog_excludes_hard_blocked():
    product_id = make_moderated_product(active_quantity=5)
    store.products[product_id].status = "HARD_BLOCKED"

    response = client.get("/api/v1/products", headers={"X-Service-Key": "development-service-key"})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_catalog_missing_service_key_returns_401():
    response = client.get("/api/v1/products")

    assert response.status_code == 401
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "Valid X-Service-Key is required",
    }


def test_catalog_response_has_no_cost_price():
    make_moderated_product(active_quantity=5)

    response = client.get("/api/v1/products", headers={"X-Service-Key": "development-service-key"})

    assert response.status_code == 200
    sku = response.json()["items"][0]["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


def test_batch_ids_returns_visible_subset():
    visible_id = make_moderated_product(active_quantity=5)
    hidden_id = make_moderated_product(active_quantity=0, title="Hidden phone")
    blocked_id = create_product(status="HARD_BLOCKED")
    ids = f"{visible_id},{hidden_id},{blocked_id},a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    response = client.get(
        f"/api/v1/products?ids={ids}",
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [visible_id]


def make_reservable_sku(active_quantity: int = 5) -> str:
    product_id = create_product()
    response = client.post(
        "/api/v1/skus", json=sku_payload(product_id), headers={"Authorization": f"Bearer {jwt_for()}"}
    )
    assert response.status_code == 201
    sku_id = response.json()["id"]
    store.products[product_id].skus[0].active_quantity = active_quantity
    return sku_id


def test_reserve_all_skus_succeeds():
    first_sku = make_reservable_sku(5)
    second_sku = make_reservable_sku(3)

    response = client.post(
        "/api/v1/reserve",
        json={
            "idempotency_key": "11111111-1111-4111-8111-111111111111",
            "items": [
                {"sku_id": first_sku, "quantity": 2},
                {"sku_id": second_sku, "quantity": 1},
            ],
        },
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert response.json()["reserved"] is True
    assert response.json()["items"][0]["remaining_stock"] == 3
    all_skus = [sku for product in store.products.values() for sku in product.skus]
    assert next(sku for sku in all_skus if sku.id == first_sku).reserved_quantity == 2


def test_partial_insufficient_stock_returns_409_all_rollback():
    first_sku = make_reservable_sku(5)
    second_sku = make_reservable_sku(1)

    response = client.post(
        "/api/v1/reserve",
        json={
            "idempotency_key": "22222222-2222-4222-8222-222222222222",
            "items": [
                {"sku_id": first_sku, "quantity": 2},
                {"sku_id": second_sku, "quantity": 2},
            ],
        },
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 409
    assert response.json()["reserved"] is False
    all_skus = [sku for product in store.products.values() for sku in product.skus]
    assert next(sku for sku in all_skus if sku.id == first_sku).active_quantity == 5
    assert next(sku for sku in all_skus if sku.id == first_sku).reserved_quantity == 0


def test_idempotent_reserve_returns_200_without_double_deduction():
    sku_id = make_reservable_sku(5)
    payload = {
        "idempotency_key": "33333333-3333-4333-8333-333333333333",
        "items": [{"sku_id": sku_id, "quantity": 2}],
    }
    headers = {"X-Service-Key": "development-service-key"}

    first = client.post("/api/v1/reserve", json=payload, headers=headers)
    second = client.post("/api/v1/reserve", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    sku = next(sku for product in store.products.values() for sku in product.skus if sku.id == sku_id)
    assert sku.active_quantity == 3
    assert sku.reserved_quantity == 2


def test_sku_out_of_stock_event_emitted():
    sku_id = make_reservable_sku(2)

    response = client.post(
        "/api/v1/reserve",
        json={
            "idempotency_key": "44444444-4444-4444-8444-444444444444",
            "items": [{"sku_id": sku_id, "quantity": 2}],
        },
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert any(event["event"] == "SKU_OUT_OF_STOCK" and event["sku_id"] == sku_id for event in store.b2c_events)


def test_unreserve_restores_quantities():
    sku_id = make_reservable_sku(5)
    reserve_response = client.post(
        "/api/v1/reserve",
        json={
            "idempotency_key": "55555555-5555-4555-8555-555555555555",
            "items": [{"sku_id": sku_id, "quantity": 3}],
        },
        headers={"X-Service-Key": "development-service-key"},
    )
    assert reserve_response.status_code == 200

    response = client.post(
        "/api/v1/unreserve",
        json={
            "order_id": "66666666-6666-4666-8666-666666666666",
            "items": [{"sku_id": sku_id, "quantity": 3}],
        },
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    sku = next(sku for product in store.products.values() for sku in product.skus if sku.id == sku_id)
    assert sku.active_quantity == 5
    assert sku.reserved_quantity == 0


def moderation_payload(product_id: str, key: str, status: str = "MODERATED", hard_block: bool = False) -> dict:
    payload = {"idempotency_key": key, "product_id": product_id, "status": status, "hard_block": hard_block}
    if status == "BLOCKED":
        payload["blocking_reason"] = {
            "id": "a7b8c9d0-1234-5678-ef01-890123456789",
            "title": "Description does not match",
            "comment": "Fix the description",
        }
        payload["field_reports"] = [{"field_name": "description", "sku_id": None, "comment": "Correct it"}]
    return payload


def test_moderated_event_clears_blocking_data():
    product_id = create_product(status="BLOCKED")
    product = store.products[product_id]
    product.blocked = True
    product.blocking_reason = BlockingReason(id="a7b8c9d0-1234-5678-ef01-890123456789", title="Old", comment="Old")
    product.field_reports = [FieldReport(field_name="description", comment="Old")]

    response = client.post(
        "/api/v1/events/moderation",
        json=moderation_payload(product_id, "77777777-7777-4777-8777-777777777777"),
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert product.status == "MODERATED"
    assert product.blocked is False
    assert product.blocking_reason is None
    assert product.field_reports == []


def test_blocked_soft_saves_field_reports():
    product_id = create_product()

    response = client.post(
        "/api/v1/events/moderation",
        json=moderation_payload(product_id, "88888888-8888-4888-8888-888888888888", "BLOCKED"),
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert store.products[product_id].status == "BLOCKED"
    assert store.products[product_id].field_reports[0].field_name == "description"
    assert store.b2c_events[-1]["event"] == "PRODUCT_BLOCKED"


def test_blocked_hard_sets_terminal_status():
    product_id = create_product()

    response = client.post(
        "/api/v1/events/moderation",
        json=moderation_payload(product_id, "99999999-9999-4999-8999-999999999999", "BLOCKED", True),
        headers={"X-Service-Key": "development-service-key"},
    )

    assert response.status_code == 200
    assert store.products[product_id].status == "HARD_BLOCKED"
    assert store.products[product_id].blocked is True
    assert store.b2c_events[-1]["event"] == "PRODUCT_BLOCKED"


def test_hard_blocked_product_rejects_seller_edits():
    product_id = create_product(status="HARD_BLOCKED")

    update = client.put(
        f"/api/v1/products/{product_id}",
        json={"title": "Changed"},
        headers={"Authorization": f"Bearer {jwt_for()}"},
    )
    delete = client.delete(
        f"/api/v1/products/{product_id}",
        headers={"Authorization": f"Bearer {jwt_for()}"},
    )

    assert update.status_code == 403
    assert delete.status_code == 403


def test_duplicate_event_same_idempotency_key_no_side_effects():
    product_id = create_product()
    payload = moderation_payload(product_id, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "BLOCKED")
    headers = {"X-Service-Key": "development-service-key"}

    first = client.post("/api/v1/events/moderation", json=payload, headers=headers)
    event_count = len(store.b2c_events)
    second = client.post("/api/v1/events/moderation", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(store.b2c_events) == event_count
    assert store.products[product_id].status == "BLOCKED"


def test_moderation_event_missing_service_key_returns_401():
    product_id = create_product()
    response = client.post(
        "/api/v1/events/moderation",
        json=moderation_payload(product_id, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    assert response.status_code == 401
