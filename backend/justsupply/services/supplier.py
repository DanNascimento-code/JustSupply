from datetime import UTC, datetime
from uuid import UUID, uuid4

from justsupply.domain.supplier import Supplier
from justsupply.repositories.supplier import SupplierRepository
from justsupply.schemas.supplier import SupplierCreate, SupplierUpdate


class SupplierNotFoundError(Exception):
    def __init__(self, supplier_id: UUID) -> None:
        super().__init__(f"Supplier '{supplier_id}' was not found.")


class SupplierAlreadyExistsError(Exception):
    def __init__(self, legal_name: str) -> None:
        super().__init__(f"A supplier named '{legal_name}' already exists.")


class SupplierService:
    def __init__(self, repository: SupplierRepository) -> None:
        self._repository = repository

    def list(self) -> list[Supplier]:
        return self._repository.list()

    def get(self, supplier_id: UUID) -> Supplier:
        supplier = self._repository.get(supplier_id)
        if supplier is None:
            raise SupplierNotFoundError(supplier_id)
        return supplier

    def create(self, payload: SupplierCreate) -> Supplier:
        if self._repository.get_by_legal_name(payload.legal_name) is not None:
            raise SupplierAlreadyExistsError(payload.legal_name)

        now = datetime.now(UTC)
        supplier = Supplier(
            id=uuid4(),
            legal_name=payload.legal_name,
            country_code=payload.country_code,
            website=payload.website,
            commodities=tuple(payload.commodities),
            created_at=now,
            updated_at=now,
        )
        return self._repository.save(supplier)

    def update(self, supplier_id: UUID, payload: SupplierUpdate) -> Supplier:
        current_supplier = self.get(supplier_id)
        supplier_with_same_name = self._repository.get_by_legal_name(payload.legal_name)
        if supplier_with_same_name is not None and supplier_with_same_name.id != supplier_id:
            raise SupplierAlreadyExistsError(payload.legal_name)

        updated_supplier = current_supplier.model_copy(
            update={
                "legal_name": payload.legal_name,
                "country_code": payload.country_code,
                "website": payload.website,
                "commodities": tuple(payload.commodities),
                "updated_at": datetime.now(UTC),
            }
        )
        return self._repository.save(updated_supplier)

    def delete(self, supplier_id: UUID) -> None:
        self.get(supplier_id)
        self._repository.delete(supplier_id)
