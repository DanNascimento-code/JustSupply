from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from justsupply.dependencies import get_supplier_service
from justsupply.main import app
from justsupply.repositories.supplier import InMemorySupplierRepository
from justsupply.services.supplier import SupplierService


@pytest.fixture
def client() -> Iterator[TestClient]:
    repository = InMemorySupplierRepository()
    service = SupplierService(repository)
    app.dependency_overrides[get_supplier_service] = lambda: service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
