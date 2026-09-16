from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, StringConstraints

from justsupply.schemas.brand_evidence import EvidenceSourceType, ReviewDecision, ReviewStatus
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus

DocumentText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=5000),
]


class DocumentMetadata(BaseModel):
    source_title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=300),
    ]
    source_provider: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=200),
    ]
    source_url: HttpUrl
    source_type: EvidenceSourceType
    published_at: datetime | None = None


class AiExtractionFinding(BaseModel):
    dimension: Literal[
        AssessmentDimension.WOMEN_WORKERS,
        AssessmentDimension.MINORITY_INCLUSION,
    ]
    status: Literal[
        AssessmentStatus.SUPPORTED,
        AssessmentStatus.MIXED,
        AssessmentStatus.CONCERN,
    ]
    statement: DocumentText
    excerpt: DocumentText
    source_location: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
    ] = None
    rationale: DocumentText


class AiExtractionOutput(BaseModel):
    findings: list[AiExtractionFinding] = Field(max_length=8)


class ExtractedFindingRead(BaseModel):
    id: UUID
    dimension: AssessmentDimension
    status: AssessmentStatus
    statement: str
    excerpt: str
    source_location: str | None
    rationale: str
    review_status: ReviewStatus
    reviewed_at: datetime | None
    published_claim_id: UUID | None


class DocumentRead(BaseModel):
    id: UUID
    brand_id: UUID
    brand_name: str
    filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    character_count: int
    source_title: str
    source_provider: str
    source_url: str
    source_type: EvidenceSourceType
    published_at: datetime | None
    model_name: str
    prompt_version: str
    extraction_status: Literal["completed", "failed"]
    chunk_count: int = 0
    created_at: datetime
    findings: list[ExtractedFindingRead] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    items: list[DocumentRead]
    total: int


class FindingReviewUpdate(BaseModel):
    decision: ReviewDecision
