from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from justsupply.dependencies import get_consumer_service
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.main import app
from justsupply.repositories.consumer_evidence import AssessedCatalogProduct, StoredResearch
from justsupply.schemas.consumer import UserLocale
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

    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        if self.error is not None:
            raise self.error
        self.saved_products.extend(products)

    def get_research(
        self,
        barcode: str,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> StoredResearch | None:
        del barcode, language
        return self.research


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
    service = ConsumerService(  # type: ignore[arg-type]
        consumer_catalog,
        consumer_evidence_repository,
    )
    app.dependency_overrides[get_consumer_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
