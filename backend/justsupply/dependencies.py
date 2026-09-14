from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from justsupply.database.session import get_database_session
from justsupply.repositories.supplier import SqlAlchemySupplierRepository
from justsupply.services.supplier import SupplierService


def get_supplier_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> SupplierService:
    repository = SqlAlchemySupplierRepository(session)
    return SupplierService(repository)
