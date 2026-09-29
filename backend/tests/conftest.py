from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from justsupply.dependencies import get_consumer_service
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.main import app
from justsupply.repositories.consumer_evidence import (
    AssessedCatalogProduct,
    CommunityReportDocumentInput,
    StoredCommunityAttachment,
    StoredCommunityReport,
    StoredCommunitySearchProduct,
    StoredLabelImage,
    StoredPublicCommunityReport,
    StoredResearch,
)
from justsupply.schemas.consumer import (
    CommunityReportCreate,
    CommunityReportSummary,
    FoodCategory,
    UserLocale,
)
from justsupply.services.consumer import ConsumerService


@dataclass
class FakeProductCatalog:
    products: list[CatalogProduct] = field(default_factory=list)
    error: Exception | None = None
    queries: list[str] = field(default_factory=list)

    def search(self, query: str) -> list[CatalogProduct]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.products


@dataclass
class FakeConsumerEvidenceRepository:
    saved_products: list[AssessedCatalogProduct] = field(default_factory=list)
    research: StoredResearch | None = None
    error: Exception | None = None
    catalog_cache: dict[str, list[CatalogProduct]] = field(default_factory=dict)
    community_reports: list[CommunityReportCreate] = field(default_factory=list)
    public_community_reports: list[StoredPublicCommunityReport] = field(default_factory=list)
    community_search_products: list[StoredCommunitySearchProduct] = field(default_factory=list)
    community_photos: dict[UUID, StoredLabelImage] = field(default_factory=dict)

    def get_catalog_search(self, query: str) -> list[CatalogProduct] | None:
        return self.catalog_cache.get(query)

    def save_catalog_search(
        self,
        query: str,
        products: Sequence[CatalogProduct],
        *,
        ttl_hours: int,
    ) -> None:
        del ttl_hours
        self.catalog_cache[query] = list(products)

    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        if self.error is not None:
            raise self.error
        self.saved_products.extend(products)

    def get_research(
        self,
        barcode: str | None,
        language: UserLocale = UserLocale.ENGLISH,
        *,
        expected_prompt_version: str | None = None,
    ) -> StoredResearch | None:
        del barcode, language, expected_prompt_version
        return self.research

    def get_community_report_summary(
        self,
        barcode: str,
        product_name: str,
    ) -> CommunityReportSummary:
        del barcode, product_name
        return CommunityReportSummary()

    def search_community_products(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[StoredCommunitySearchProduct]:
        del query
        return self.community_search_products[:limit]

    def save_community_report(
        self,
        report: CommunityReportCreate,
        *,
        photo_data: bytes | None,
        photo_mime_type: str | None,
        documents: Sequence[CommunityReportDocumentInput] = (),
    ) -> StoredCommunityReport:
        self.community_reports.append(report)
        report_id = uuid4()
        submitted_at = datetime.now(UTC)
        attachments = tuple(
            StoredCommunityAttachment(
                id=uuid4(),
                file_name=document.file_name,
                mime_type=document.mime_type,
                data=document.data,
            )
            for document in documents
        )
        self.public_community_reports.append(
            StoredPublicCommunityReport(
                id=report_id,
                product_name=report.product_name,
                barcode=report.barcode,
                category=report.category,
                assessments=tuple(report.assessments),
                observations=report.details,
                evidence_urls=tuple(str(url) for url in report.evidence_urls),
                has_photo=photo_data is not None,
                documents=attachments,
                published_at=submitted_at,
            )
        )
        if photo_data is not None and photo_mime_type is not None:
            self.community_photos[report_id] = StoredLabelImage(
                data=photo_data,
                mime_type=photo_mime_type,
            )
        return StoredCommunityReport(
            id=report_id,
            submitted_at=submitted_at,
            document_count=len(documents),
        )

    def list_public_community_reports(
        self,
        *,
        barcode: str | None = None,
        product_name: str | None = None,
        category: FoodCategory | None = None,
        limit: int = 50,
    ) -> list[StoredPublicCommunityReport]:
        return [
            report
            for report in self.public_community_reports
            if (barcode is None or report.barcode == barcode)
            and (product_name is None or report.product_name == product_name)
            and (category is None or report.category == category)
        ][:limit]

    def get_public_community_report_photo(
        self,
        report_id: UUID,
    ) -> StoredLabelImage | None:
        return self.community_photos.get(report_id)

    def get_public_community_report_document(
        self,
        report_id: UUID,
        attachment_id: UUID,
    ) -> StoredCommunityAttachment | None:
        return next(
            (
                document
                for report in self.public_community_reports
                if report.id == report_id
                for document in report.documents
                if document.id == attachment_id
            ),
            None,
        )


@pytest.fixture
def consumer_catalog() -> FakeProductCatalog:
    return FakeProductCatalog()


@pytest.fixture
def consumer_evidence_repository() -> FakeConsumerEvidenceRepository:
    return FakeConsumerEvidenceRepository()


@pytest.fixture
def client(
    consumer_catalog: FakeProductCatalog,
    consumer_evidence_repository: FakeConsumerEvidenceRepository,
) -> Iterator[TestClient]:
    service = ConsumerService(
        consumer_catalog,
        consumer_evidence_repository,  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_consumer_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
