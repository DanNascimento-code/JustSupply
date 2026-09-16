from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from justsupply.dependencies import get_brand_evidence_service
from justsupply.repositories.brand_evidence import BrandClaimNotFoundError, BrandNotFoundError
from justsupply.repositories.consumer_evidence import EvidencePersistenceError
from justsupply.schemas.brand_evidence import (
    BrandClaimListResponse,
    BrandClaimRead,
    BrandEvidenceCreate,
    BrandListResponse,
    ClaimReviewUpdate,
)
from justsupply.services.brand_evidence import BrandEvidenceService

router = APIRouter(prefix="/evidence", tags=["evidence"])
BrandEvidenceServiceDependency = Annotated[
    BrandEvidenceService,
    Depends(get_brand_evidence_service),
]


@router.get("/brands", response_model=BrandListResponse)
def list_brands(service: BrandEvidenceServiceDependency) -> BrandListResponse:
    return service.list_brands()


@router.get("/brands/{brand_id}/claims", response_model=BrandClaimListResponse)
def list_brand_claims(
    brand_id: UUID,
    service: BrandEvidenceServiceDependency,
) -> BrandClaimListResponse:
    try:
        return service.list_claims(brand_id)
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post(
    "/brands/{brand_id}/claims",
    response_model=BrandClaimRead,
    status_code=status.HTTP_201_CREATED,
)
def create_brand_claim(
    brand_id: UUID,
    payload: BrandEvidenceCreate,
    service: BrandEvidenceServiceDependency,
) -> BrandClaimRead:
    try:
        return service.create_claim(brand_id, payload)
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except EvidencePersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.patch("/claims/{claim_id}/review", response_model=BrandClaimRead)
def review_brand_claim(
    claim_id: UUID,
    payload: ClaimReviewUpdate,
    service: BrandEvidenceServiceDependency,
) -> BrandClaimRead:
    try:
        return service.review_claim(claim_id, payload)
    except (BrandClaimNotFoundError, BrandNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
