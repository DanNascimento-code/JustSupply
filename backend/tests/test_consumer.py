from datetime import UTC, datetime

from fastapi.testclient import TestClient

from justsupply.integrations.open_food_facts import (
    CatalogProduct,
    CatalogUnavailableError,
)
from justsupply.repositories.consumer_evidence import EvidencePersistenceError
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    ConsumerAssessment,
    EvidenceScope,
)


def catalog_product(
    *,
    vegan_tag: str = "en:vegan",
    environmental_grade: str | None = "b",
) -> CatalogProduct:
    return CatalogProduct(
        barcode="7891000100103",
        name="Dark chocolate",
        brand="Example Foods",
        image_url="https://images.openfoodfacts.org/product.jpg",
        ingredients_analysis_tags=frozenset({vegan_tag}),
        environmental_score_grade=environmental_grade,
        last_updated_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        source_url="https://world.openfoodfacts.org/product/7891000100103",
    )


def test_search_product_by_barcode(
    client: TestClient,
    consumer_catalog: object,
    consumer_evidence_repository: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]

    response = client.get("/api/v1/consumer/products", params={"query": "7891000100103"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_type"] == "barcode"
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Dark chocolate"
    assert payload["items"][0]["evidence_coverage_percent"] == 50
    assessments = payload["items"][0]["assessments"]
    assert [assessment["status"] for assessment in assessments] == [
        "supported",
        "supported",
        "not_disclosed",
        "not_disclosed",
    ]
    assert len(consumer_evidence_repository.saved_products) == 1  # type: ignore[attr-defined]


def test_text_search_preserves_the_query(client: TestClient, consumer_catalog: object) -> None:
    consumer_catalog.products = [  # type: ignore[attr-defined]
        catalog_product(vegan_tag="en:non-vegan", environmental_grade="e")
    ]

    response = client.get("/api/v1/consumer/products", params={"query": "  Example  "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Example"
    assert payload["query_type"] == "text"
    assert payload["items"][0]["assessments"][0]["status"] == "concern"
    assert payload["items"][0]["assessments"][1]["status"] == "concern"


def test_search_returns_an_empty_result(client: TestClient) -> None:
    response = client.get("/api/v1/consumer/products", params={"query": "unknown product"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_catalog_failure_becomes_bad_gateway(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.error = CatalogUnavailableError("Catalog unavailable.")  # type: ignore[attr-defined]

    response = client.get("/api/v1/consumer/products", params={"query": "coffee"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Catalog unavailable."


def test_evidence_failure_becomes_service_unavailable(
    client: TestClient,
    consumer_catalog: object,
    consumer_evidence_repository: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]
    consumer_evidence_repository.error = EvidencePersistenceError(  # type: ignore[attr-defined]
        "Evidence snapshot unavailable."
    )

    response = client.get("/api/v1/consumer/products", params={"query": "coffee"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Evidence snapshot unavailable."


def test_approved_brand_evidence_replaces_the_disclosure_gap(
    client: TestClient,
    consumer_catalog: object,
    consumer_evidence_repository: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]
    consumer_evidence_repository.approved_assessments = {  # type: ignore[attr-defined]
        AssessmentDimension.WOMEN_WORKERS: ConsumerAssessment(
            dimension=AssessmentDimension.WOMEN_WORKERS,
            title="Women workers",
            status=AssessmentStatus.SUPPORTED,
            finding="A reviewed report documents a leadership program for women workers.",
            evidence_scope=EvidenceScope.BRAND,
            sources=[
                AssessmentSourceRead(
                    title="2025 Impact Report",
                    provider_name="Example Organization",
                    url="https://example.org/report",
                    published_at=datetime(2025, 12, 1, tzinfo=UTC),
                    source_location="page 18",
                )
            ],
        )
    }

    response = client.get("/api/v1/consumer/products", params={"query": "Example Foods"})

    assert response.status_code == 200
    product = response.json()["items"][0]
    women_assessment = product["assessments"][2]
    assert women_assessment["status"] == "supported"
    assert women_assessment["sources"][0]["provider_name"] == "Example Organization"
    assert product["evidence_coverage_percent"] == 75


def test_rejects_a_query_that_is_too_short(client: TestClient) -> None:
    response = client.get("/api/v1/consumer/products", params={"query": "a"})

    assert response.status_code == 422
