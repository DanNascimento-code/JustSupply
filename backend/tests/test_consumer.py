from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from justsupply.dependencies import get_consumer_research_service
from justsupply.integrations.open_food_facts import CatalogProduct, CatalogUnavailableError
from justsupply.main import app
from justsupply.repositories.consumer_evidence import (
    EvidencePersistenceError,
    StoredCommunitySearchProduct,
)
from justsupply.schemas.consumer import (
    AssessmentDimension,
    CommunityReportOutcomeCounts,
    CommunityReportSummary,
    ConsumerAnswerResponse,
    ConsumerProductRead,
    FoodCategory,
    ProductResearchResponse,
    UserLocale,
)
from justsupply.services.consumer import ConsumerResearchService


def catalog_product(
    *,
    vegan_tag: str = "en:vegan",
    environmental_grade: str | None = "b",
    ingredients_text: str | None = None,
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
        ingredients_text=ingredients_text,
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


def test_ingredient_fallback_detects_animal_derived_content(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.products = [  # type: ignore[attr-defined]
        catalog_product(vegan_tag="en:vegan-status-unknown", ingredients_text="Cocoa, milk, sugar")
    ]

    response = client.get("/api/v1/consumer/products", params={"query": "milk chocolate"})

    assessment = response.json()["items"][0]["assessments"][0]
    assert assessment["status"] == "concern"
    assert "milk" in assessment["finding"]


def test_catalog_search_is_reused_from_database_cache(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]

    first = client.get("/api/v1/consumer/products", params={"query": "Example"})
    consumer_catalog.products = []  # type: ignore[attr-defined]
    second = client.get("/api/v1/consumer/products", params={"query": "Example"})

    assert first.status_code == 200
    assert second.json()["total"] == 1
    assert consumer_catalog.queries == ["Example"]  # type: ignore[attr-defined]


def test_degraded_catalog_search_is_not_cached(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.products = [  # type: ignore[attr-defined]
        replace(
            catalog_product(environmental_grade=None, ingredients_text="Corn, salt"),
            source_name="USDA FoodData Central",
            catalog_degraded=True,
        )
    ]

    first = client.get("/api/v1/consumer/products", params={"query": "Example"})
    second = client.get("/api/v1/consumer/products", params={"query": "Example"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert consumer_catalog.queries == ["Example", "Example"]  # type: ignore[attr-defined]
    environmental = first.json()["items"][0]["assessments"][1]
    assert environmental["verification"] == "unverified"
    assert environmental["sources"] == []
    assert "Open Food Facts" in environmental["finding"]
    assert "USDA FoodData Central" in environmental["verification_note"]


def test_empty_search_result(client: TestClient) -> None:
    response = client.get("/api/v1/consumer/products", params={"query": "unknown product"})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_main_search_includes_community_only_product(
    client: TestClient,
    consumer_evidence_repository: object,
) -> None:
    consumer_evidence_repository.community_search_products = [  # type: ignore[attr-defined]
        StoredCommunitySearchProduct(
            report_id=uuid4(),
            product_name="Community oat yogurt",
            barcode=None,
            category=FoodCategory.YOGURT,
            has_photo=True,
            published_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            summary=CommunityReportSummary(
                total=2,
                assessment_counts={
                    AssessmentDimension.VEGAN_COMPOSITION: CommunityReportOutcomeCounts(
                        positive=2,
                        negative=0,
                    )
                },
            ),
        )
    ]

    response = client.get(
        "/api/v1/consumer/products",
        params={"query": "Community oat yogurt"},
    )

    assert response.status_code == 200
    product = response.json()["items"][0]
    assert product["name"] == "Community oat yogurt"
    assert product["catalog_product"] is False
    assert product["category"] == "yogurt"
    assert product["community_reports"]["assessment_counts"]["vegan_composition"] == {
        "positive": 2,
        "negative": 0,
    }


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


def test_accepts_unverified_community_report(
    client: TestClient,
    consumer_evidence_repository: object,
) -> None:
    response = client.post(
        "/api/v1/consumer/reports",
        data={
            "product_name": "Example drink",
            "barcode": "7891000100103",
            "category": "beverages",
            "vegan_composition": "negative",
            "environmental_impact": "positive",
            "details": "The label lists an ingredient that should be independently reviewed.",
            "evidence_urls": [
                "https://example.org/product-source",
                "https://news.example.org/product-report",
            ],
        },
        files=[
            ("photo", ("product.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")),
            (
                "documents",
                ("evidence.pdf", b"%PDF-1.7\ncontent", "application/pdf"),
            ),
        ],
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "published_unverified"
    assert payload["has_photo"] is True
    assert payload["document_count"] == 1
    assert payload["category"] == "beverages"
    saved_report = consumer_evidence_repository.community_reports[0]  # type: ignore[attr-defined]
    assert [str(url) for url in saved_report.evidence_urls] == [
        "https://example.org/product-source",
        "https://news.example.org/product-report",
    ]
    assert payload["assessments"] == [
        {"dimension": "vegan_composition", "outcome": "negative"},
        {"dimension": "environmental_impact", "outcome": "positive"},
    ]
    assert len(consumer_evidence_repository.community_reports) == 1  # type: ignore[attr-defined]

    listing = client.get(
        "/api/v1/consumer/reports",
        params={"barcode": "7891000100103", "category": "beverages"},
    )
    assert listing.status_code == 200
    public_report = listing.json()["items"][0]
    assert public_report["observations"].startswith("The label lists")
    assert public_report["status"] == "published_unverified"
    assert public_report["category"] == "beverages"
    assert public_report["assessments"] == payload["assessments"]
    assert public_report["evidence_urls"] == [
        "https://example.org/product-source",
        "https://news.example.org/product-report",
    ]
    assert public_report["photo_url"] is not None
    assert public_report["documents"][0]["file_name"] == "evidence.pdf"

    photo = client.get(public_report["photo_url"])
    document = client.get(public_report["documents"][0]["download_url"])
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"
    assert document.status_code == 200
    assert "attachment" in document.headers["content-disposition"]
    mismatched_category = client.get(
        "/api/v1/consumer/reports",
        params={"category": "ice_cream"},
    )
    assert mismatched_category.json()["total"] == 0


def test_community_report_requires_identity_and_assessment(client: TestClient) -> None:
    missing_identity = client.post(
        "/api/v1/consumer/reports",
        data={
            "vegan_composition": "positive",
            "category": "beverages",
            "details": "This report has enough explanatory detail.",
        },
    )
    missing_assessment = client.post(
        "/api/v1/consumer/reports",
        data={
            "product_name": "Example drink",
            "category": "beverages",
            "details": "This report has enough explanatory detail.",
        },
    )

    assert missing_identity.status_code == 422
    assert missing_assessment.status_code == 422


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

    def research_label(
        self,
        barcode: str,
        image_data: bytes,
        mime_type: str,
        *,
        language: UserLocale,
    ) -> ProductResearchResponse:
        assert barcode == self.product.barcode
        assert image_data.startswith(b"\x89PNG")
        assert mime_type == "image/png"
        assert language == UserLocale.ENGLISH
        return ProductResearchResponse(product=self.product, cached=False)


def test_ask_automatically_ensures_research_before_using_rag() -> None:
    expected = ConsumerAnswerResponse(
        question="What evidence is available?",
        answer="The persisted evidence supports this answer [1].",
        insufficient_evidence=False,
        citations=[],
        retrieval_model="embedding-test",
        generation_model="gemini-test",
        prompt_version="rag-test",
        cached=True,
    )

    class RepositoryStub:
        def get_research(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            return None

        def get_cached_answer(self, *args: object, **kwargs: object) -> ConsumerAnswerResponse:
            del args, kwargs
            return expected

    service = ConsumerResearchService.__new__(ConsumerResearchService)
    service._repository = RepositoryStub()  # type: ignore[assignment]
    service._researcher = type("ResearcherStub", (), {"prompt_version": "research-v7"})()  # type: ignore[assignment]
    research_calls: list[str] = []
    service.research = lambda barcode, **kwargs: research_calls.append(barcode)  # type: ignore[method-assign,assignment]

    response = service.ask(
        "7891000100103",
        "What evidence is available?",
        top_k=4,
        language=UserLocale.ENGLISH,
    )

    assert research_calls == ["7891000100103"]
    assert response == expected


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
        label = client.post(
            f"/api/v1/consumer/products/{product.barcode}/research-label",
            files={"image": ("label.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_consumer_research_service, None)

    assert research.status_code == 200
    assert research.json()["cached"] is False
    assert answer.status_code == 200
    assert answer.json()["insufficient_evidence"] is True
    assert label.status_code == 200


def test_rejects_invalid_label_upload(
    client: TestClient,
    consumer_catalog: object,
) -> None:
    consumer_catalog.products = [catalog_product()]  # type: ignore[attr-defined]
    search = client.get("/api/v1/consumer/products", params={"query": "7891000100103"})
    product = ConsumerProductRead.model_validate(search.json()["items"][0])
    app.dependency_overrides[get_consumer_research_service] = lambda: StubResearchService(product)
    try:
        response = client.post(
            f"/api/v1/consumer/products/{product.barcode}/research-label",
            files={"image": ("label.png", b"not-an-image", "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_consumer_research_service, None)

    assert response.status_code == 422


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
