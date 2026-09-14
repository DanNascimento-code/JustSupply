from typing import Protocol
from uuid import UUID

from justsupply.domain.supplier import Supplier


class SupplierRepository(Protocol):
    def list(self) -> list[Supplier]: ...

    def get(self, supplier_id: UUID) -> Supplier | None: ...

    def get_by_legal_name(self, legal_name: str) -> Supplier | None: ...

    def save(self, supplier: Supplier) -> Supplier: ...

    def delete(self, supplier_id: UUID) -> None: ...


class InMemorySupplierRepository:
    def __init__(self) -> None:
        self._suppliers: dict[UUID, Supplier] = {}

    def list(self) -> list[Supplier]:
        return sorted(
            self._suppliers.values(),
            key=lambda supplier: supplier.legal_name.casefold(),
        )

    def get(self, supplier_id: UUID) -> Supplier | None:
        return self._suppliers.get(supplier_id)

    def get_by_legal_name(self, legal_name: str) -> Supplier | None:
        normalized_name = legal_name.casefold()
        return next(
            (
                supplier
                for supplier in self._suppliers.values()
                if supplier.legal_name.casefold() == normalized_name
            ),
            None,
        )

    def save(self, supplier: Supplier) -> Supplier:
        self._suppliers[supplier.id] = supplier
        return supplier

    def delete(self, supplier_id: UUID) -> None:
        del self._suppliers[supplier_id]
