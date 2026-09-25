from datetime import UTC, datetime

from fastapi.testclient import TestClient

from justsupply.dependencies import get_consumer_research_service
from justsupply.integrations.open_food_facts import CatalogProduct, CatalogUnavailableError
from justsupply.main import app
from justsupply.repositories.consumer_evidence import EvidencePersistenceError
from justsupply.schemas.consumer import (
    ConsumerAnswerResponse,
    ConsumerProductRead,
    ProductResearchResponse,
    UserLocale,
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
    product = response.json()["items"][0]
    assert product["name"] == "Dark chocolate"
    assert product["image_url"].endswith("product.jpg")
    assert product["evidence_coverage_percent"] == 50
    assert [item["status"] for item in product["assessments"]] == [
        "supported",
        "supported",
        "not_disclosed",
        "not_disclosed",
    ]
    assert product["assessments"][0]["verification"] == "catalog_data"
    assert product["assessments"][2]["verification"] == "unverified"
    assert len(consumer_evidence_repository.saved_products) == 1  # type: ignore[attr-defined]


def test_text_search_preserves_query_and_concerns(
    client: TestClient,
    consumer_catalog: object,
) -> None:
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


def test_empty_search_result(client: TestClient) -> None:
    response = client.get("/api/v1/consumer/products", params={"query": "unknown product"})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_catalog_failure_becomes_bad_gateway(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.error = CatalogUnavailableError("Catalog unavailable.")  # type: ignore[attr-defined]
    response = client.get("/api/v1/consumer/products", params={"query": "coffee"})
    assert response.status_code == 502


def test_persistence_failure_becomes_service_unavailable(
    client: TestClient,
    consumer_catalog: object,
    consumer_evidence_repository: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]
    consumer_evidence_repository.error = EvidencePersistenceError("Database unavailable.")  # type: ignore[attr-defined]
    response = client.get("/api/v1/consumer/products", params={"query": "coffee"})
    assert response.status_code == 503


def test_rejects_short_query(client: TestClient) -> None:
    response = client.get("/api/v1/consumer/products", params={"query": "a"})
    assert response.status_code == 422


class StubResearchService:
    def __init__(self, product: ConsumerProductRead) -> None:
        self.product = product

    def research(
        self,
        barcode: str,
        *,
        refresh: bool,
        language: UserLocale,
    ) -> ProductResearchResponse:
        assert barcode == self.product.barcode
        assert refresh is False
        assert language == UserLocale.ENGLISH
        return ProductResearchResponse(product=self.product, cached=False)

    def ask(
        self,
        barcode: str,
        question: str,
        *,
        top_k: int,
        language: UserLocale,
    ) -> ConsumerAnswerResponse:
        assert barcode == self.product.barcode
        assert question == "Is the available evidence sufficient?"
        assert top_k == 4
        assert language == UserLocale.ENGLISH
        return ConsumerAnswerResponse(
            question=question,
            answer="The saved evidence is not sufficient.",
            insufficient_evidence=True,
            citations=[],
            retrieval_model="gemini-embedding-test",
            generation_model="gemini-test",
            prompt_version="consumer-evidence-rag-v1",
        )


def test_research_and_question_routes(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]
    search = client.get("/api/v1/consumer/products", params={"query": "7891000100103"})
    product = ConsumerProductRead.model_validate(search.json()["items"][0])
    app.dependency_overrides[get_consumer_research_service] = lambda: StubResearchService(product)
    try:
        research = client.post(f"/api/v1/consumer/products/{product.barcode}/research")
        answer = client.post(
            f"/api/v1/consumer/products/{product.barcode}/ask",
            json={"question": "Is the available evidence sufficient?", "top_k": 4},
        )
    finally:
        app.dependency_overrides.pop(get_consumer_research_service, None)

    assert research.status_code == 200
    assert research.json()["cached"] is False
    assert answer.status_code == 200
    assert answer.json()["insufficient_evidence"] is True


def test_search_can_return_brazilian_portuguese_catalog_assessments(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]

    response = client.get(
        "/api/v1/consumer/products",
        params={"query": "7891000100103", "language": "pt-BR"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["assessments"][0]["title"] == "Composição vegana"
    assert "ausência de informação" in payload["disclaimer"]
