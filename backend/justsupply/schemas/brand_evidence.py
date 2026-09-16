from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, StringConstraints, field_validator

from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
)

EvidenceText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=10, max_length=2000),
]
SourceTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=300),
]


class EvidenceSourceType(StrEnum):
    CORPORATE_REPORT = "corporate_report"
    CERTIFICATION = "certification"
    NGO_REPORT = "ngo_report"
    NEWS = "news"
    ACADEMIC_RESEARCH = "academic_research"
    PUBLIC_DATABASE = "public_database"
    OTHER = "other"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class BrandSummaryRead(BaseModel):
    id: UUID
    name: str


class BrandListResponse(BaseModel):
    items: list[BrandSummaryRead]
    total: int


class BrandEvidenceCreate(BaseModel):
    dimension: AssessmentDimension
    status: AssessmentStatus
    statement: EvidenceText
    source_title: SourceTitle
    source_provider: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=200),
    ]
    source_url: HttpUrl
    source_type: EvidenceSourceType
    excerpt: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=5000)] = None
    source_location: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
    ] = None
    published_at: datetime | None = None

    @field_validator("dimension")
    @classmethod
    def require_social_dimension(
        cls,
        dimension: AssessmentDimension,
    ) -> AssessmentDimension:
        allowed_dimensions = {
            AssessmentDimension.WOMEN_WORKERS,
            AssessmentDimension.MINORITY_INCLUSION,
        }
        if dimension not in allowed_dimensions:
            raise ValueError("Only social evidence dimensions can be submitted here.")
        return dimension

    @field_validator("status")
    @classmethod
    def require_evidence_finding(
        cls,
        finding_status: AssessmentStatus,
    ) -> AssessmentStatus:
        allowed_statuses = {
            AssessmentStatus.SUPPORTED,
            AssessmentStatus.MIXED,
            AssessmentStatus.CONCERN,
        }
        if finding_status not in allowed_statuses:
            raise ValueError("Evidence must support, mix, or raise a concern.")
        return finding_status


class ClaimReviewUpdate(BaseModel):
    decision: ReviewDecision


class BrandClaimRead(BaseModel):
    id: UUID
    brand_id: UUID
    brand_name: str
    dimension: AssessmentDimension
    status: AssessmentStatus
    statement: str
    review_status: ReviewStatus
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    sources: list[AssessmentSourceRead] = Field(default_factory=list)


class BrandClaimListResponse(BaseModel):
    items: list[BrandClaimRead]
    total: int
