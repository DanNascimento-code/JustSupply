from typing import Protocol
from uuid import UUID

from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from justsupply.database.models import SupplierModel
from justsupply.domain.supplier import Commodity, Supplier


class SupplierNameConflictError(Exception):
    def __init__(self, legal_name: str) -> None:
        super().__init__(legal_name)


class SupplierRepository(Protocol):
    def list(self) -> list[Supplier]: ...

    def get(self, supplier_id: UUID) -> Supplier | None: ...

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

    def save(self, supplier: Supplier) -> Supplier:
        normalized_name = supplier.legal_name.casefold()
        has_conflict = any(
            existing_supplier.id != supplier.id
            and existing_supplier.legal_name.casefold() == normalized_name
            for existing_supplier in self._suppliers.values()
        )
        if has_conflict:
            raise SupplierNameConflictError(supplier.legal_name)

        self._suppliers[supplier.id] = supplier
        return supplier

    def delete(self, supplier_id: UUID) -> None:
        del self._suppliers[supplier_id]


class SqlAlchemySupplierRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[Supplier]:
        statement = select(SupplierModel).order_by(SupplierModel.legal_name.asc())
        models = self._session.scalars(statement).all()
        return [self._to_domain(model) for model in models]

    def get(self, supplier_id: UUID) -> Supplier | None:
        model = self._session.get(SupplierModel, supplier_id)
        if model is None:
            return None
        return self._to_domain(model)

    def save(self, supplier: Supplier) -> Supplier:
        model = self._session.get(SupplierModel, supplier.id)
        if model is None:
            model = SupplierModel(id=supplier.id)
            self._session.add(model)

        model.legal_name = supplier.legal_name
        model.legal_name_key = supplier.legal_name.casefold()
        model.country_code = supplier.country_code
        model.website = str(supplier.website) if supplier.website is not None else None
        model.commodities = [commodity.value for commodity in supplier.commodities]
        model.created_at = supplier.created_at
        model.updated_at = supplier.updated_at

        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise SupplierNameConflictError(supplier.legal_name) from error

        self._session.refresh(model)
        return self._to_domain(model)

    def delete(self, supplier_id: UUID) -> None:
        model = self._session.get(SupplierModel, supplier_id)
        if model is None:
            return
        self._session.delete(model)
        self._session.commit()

    @staticmethod
    def _to_domain(model: SupplierModel) -> Supplier:
        return Supplier(
            id=model.id,
            legal_name=model.legal_name,
            country_code=model.country_code,
            website=HttpUrl(model.website) if model.website is not None else None,
            commodities=tuple(Commodity(value) for value in model.commodities),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
