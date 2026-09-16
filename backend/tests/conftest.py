from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from justsupply.dependencies import get_consumer_service, get_supplier_service
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.main import app
from justsupply.repositories.consumer_evidence import AssessedCatalogProduct
from justsupply.repositories.supplier import InMemorySupplierRepository
from justsupply.schemas.consumer import AssessmentDimension, ConsumerAssessment
from justsupply.services.consumer import ConsumerService
from justsupply.services.supplier import SupplierService


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
    approved_assessments: dict[AssessmentDimension, ConsumerAssessment] = field(
        default_factory=dict
    )
    error: Exception | None = None

    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        if self.error is not None:
            raise self.error
        self.saved_products.extend(products)

    def approved_brand_assessments(
        self,
        brand_names: str | None,
    ) -> dict[AssessmentDimension, ConsumerAssessment]:
        del brand_names
        return self.approved_assessments


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
    repository = InMemorySupplierRepository()
    supplier_service = SupplierService(repository)
    consumer_service = ConsumerService(consumer_catalog, consumer_evidence_repository)
    app.dependency_overrides[get_supplier_service] = lambda: supplier_service
    app.dependency_overrides[get_consumer_service] = lambda: consumer_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
