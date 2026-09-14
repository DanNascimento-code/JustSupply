from uuid import UUID

from fastapi.testclient import TestClient


def supplier_payload(
    legal_name: str = "Cooperativa Cacau Justo",
) -> dict[str, str | list[str]]:
    return {
        "legal_name": legal_name,
        "country_code": "br",
        "website": "https://example.org",
        "commodities": ["cocoa", "coffee", "cocoa"],
    }


def test_create_and_list_supplier(client: TestClient) -> None:
    create_response = client.post("/api/v1/suppliers", json=supplier_payload())

    assert create_response.status_code == 201
    created_supplier = create_response.json()
    UUID(created_supplier["id"])
    assert created_supplier["legal_name"] == "Cooperativa Cacau Justo"
    assert created_supplier["country_code"] == "BR"
    assert created_supplier["website"] == "https://example.org/"
    assert created_supplier["commodities"] == ["cocoa", "coffee"]

    list_response = client.get("/api/v1/suppliers")

    assert list_response.status_code == 200
    assert list_response.json() == {
        "items": [created_supplier],
        "total": 1,
    }


def test_get_supplier_by_id(client: TestClient) -> None:
    created_supplier = client.post("/api/v1/suppliers", json=supplier_payload()).json()

    response = client.get(f"/api/v1/suppliers/{created_supplier['id']}")

    assert response.status_code == 200
    assert response.json() == created_supplier


def test_reject_duplicate_supplier_name(client: TestClient) -> None:
    client.post("/api/v1/suppliers", json=supplier_payload())

    response = client.post(
        "/api/v1/suppliers",
        json=supplier_payload("cooperativa cacau justo"),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "A supplier named 'cooperativa cacau justo' already exists."
    )


def test_update_supplier(client: TestClient) -> None:
    created_supplier = client.post("/api/v1/suppliers", json=supplier_payload()).json()
    updated_payload = {
        "legal_name": "Cooperativa Café Justo",
        "country_code": "co",
        "website": None,
        "commodities": ["coffee"],
    }

    response = client.put(
        f"/api/v1/suppliers/{created_supplier['id']}",
        json=updated_payload,
    )

    assert response.status_code == 200
    updated_supplier = response.json()
    assert updated_supplier["legal_name"] == "Cooperativa Café Justo"
    assert updated_supplier["country_code"] == "CO"
    assert updated_supplier["website"] is None
    assert updated_supplier["commodities"] == ["coffee"]
    assert updated_supplier["created_at"] == created_supplier["created_at"]


def test_delete_supplier(client: TestClient) -> None:
    created_supplier = client.post("/api/v1/suppliers", json=supplier_payload()).json()
    supplier_url = f"/api/v1/suppliers/{created_supplier['id']}"

    delete_response = client.delete(supplier_url)
    get_response = client.get(supplier_url)

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert get_response.status_code == 404


def test_reject_invalid_supplier_data(client: TestClient) -> None:
    payload = supplier_payload()
    payload["country_code"] = "Brazil"
    payload["commodities"] = []

    response = client.post("/api/v1/suppliers", json=payload)

    assert response.status_code == 422
