import os
from uuid import uuid4

import pytest

from justsupply.database.session import SessionFactory
from justsupply.repositories.supplier import SqlAlchemySupplierRepository
from justsupply.schemas.supplier import SupplierCreate
from justsupply.services.supplier import SupplierAlreadyExistsError, SupplierService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="Set RUN_DATABASE_TESTS=1 to run PostgreSQL integration tests.",
    ),
]


def test_supplier_repository_round_trip() -> None:
    unique_name = f"Integration Supplier {uuid4()}"

    with SessionFactory() as session:
        service = SupplierService(SqlAlchemySupplierRepository(session))
        supplier = service.create(
            SupplierCreate(
                legal_name=unique_name,
                country_code="BR",
                website="https://example.org",
                commodities=["cocoa"],
            )
        )

        try:
            stored_supplier = service.get(supplier.id)
            assert stored_supplier.legal_name == unique_name
            assert stored_supplier.country_code == "BR"
        finally:
            service.delete(supplier.id)


def test_supplier_repository_rejects_duplicate_legal_names() -> None:
    unique_name = f"Duplicate Supplier {uuid4()}"

    with SessionFactory() as session:
        service = SupplierService(SqlAlchemySupplierRepository(session))
        supplier = service.create(
            SupplierCreate(
                legal_name=unique_name,
                country_code="BR",
                website=None,
                commodities=["coffee"],
            )
        )

        try:
            with pytest.raises(SupplierAlreadyExistsError):
                service.create(
                    SupplierCreate(
                        legal_name=unique_name.lower(),
                        country_code="CO",
                        website=None,
                        commodities=["coffee"],
                    )
                )
        finally:
            service.delete(supplier.id)
