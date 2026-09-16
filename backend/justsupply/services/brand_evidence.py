from uuid import UUID

from justsupply.repositories.brand_evidence import SqlAlchemyBrandEvidenceRepository
from justsupply.schemas.brand_evidence import (
    BrandClaimListResponse,
    BrandClaimRead,
    BrandEvidenceCreate,
    BrandListResponse,
    ClaimReviewUpdate,
)


class BrandEvidenceService:
    def __init__(self, repository: SqlAlchemyBrandEvidenceRepository) -> None:
        self._repository = repository

    def list_brands(self) -> BrandListResponse:
        brands = self._repository.list_brands()
        return BrandListResponse(items=brands, total=len(brands))

    def list_claims(self, brand_id: UUID) -> BrandClaimListResponse:
        claims = self._repository.list_claims(brand_id)
        return BrandClaimListResponse(items=claims, total=len(claims))

    def create_claim(
        self,
        brand_id: UUID,
        payload: BrandEvidenceCreate,
    ) -> BrandClaimRead:
        return self._repository.create_claim(brand_id, payload)

    def review_claim(
        self,
        claim_id: UUID,
        payload: ClaimReviewUpdate,
    ) -> BrandClaimRead:
        return self._repository.review_claim(claim_id, payload.decision)
