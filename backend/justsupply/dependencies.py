from justsupply.repositories.supplier import InMemorySupplierRepository
from justsupply.services.supplier import SupplierService

supplier_repository = InMemorySupplierRepository()
supplier_service = SupplierService(supplier_repository)


def get_supplier_service() -> SupplierService:
    return supplier_service
