from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from justsupply.dependencies import get_supplier_service
from justsupply.domain.supplier import Supplier
from justsupply.schemas.supplier import (
    SupplierCreate,
    SupplierListResponse,
    SupplierRead,
    SupplierUpdate,
)
from justsupply.services.supplier import (
    SupplierAlreadyExistsError,
    SupplierNotFoundError,
    SupplierService,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])
SupplierServiceDependency = Annotated[SupplierService, Depends(get_supplier_service)]


def supplier_to_response(supplier: Supplier) -> SupplierRead:
    return SupplierRead.model_validate(supplier)


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: SupplierCreate,
    service: SupplierServiceDependency,
) -> SupplierRead:
    try:
        supplier = service.create(payload)
    except SupplierAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    return supplier_to_response(supplier)


@router.get("", response_model=SupplierListResponse)
def list_suppliers(service: SupplierServiceDependency) -> SupplierListResponse:
    suppliers = [supplier_to_response(item) for item in service.list()]
    return SupplierListResponse(items=suppliers, total=len(suppliers))


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(
    supplier_id: UUID,
    service: SupplierServiceDependency,
) -> SupplierRead:
    try:
        supplier = service.get(supplier_id)
    except SupplierNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return supplier_to_response(supplier)


@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: UUID,
    payload: SupplierUpdate,
    service: SupplierServiceDependency,
) -> SupplierRead:
    try:
        supplier = service.update(supplier_id, payload)
    except SupplierNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except SupplierAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    return supplier_to_response(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: UUID,
    service: SupplierServiceDependency,
) -> Response:
    try:
        service.delete(supplier_id)
    except SupplierNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
