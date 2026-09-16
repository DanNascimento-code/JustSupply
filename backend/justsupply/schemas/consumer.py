from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SearchQueryType(StrEnum):
    BARCODE = "barcode"
    TEXT = "text"


class AssessmentDimension(StrEnum):
    VEGAN_COMPOSITION = "vegan_composition"
    ENVIRONMENTAL_IMPACT = "environmental_impact"
    WOMEN_WORKERS = "women_workers"
    MINORITY_INCLUSION = "minority_inclusion"


class AssessmentStatus(StrEnum):
    SUPPORTED = "supported"
    MIXED = "mixed"
    CONCERN = "concern"
    NOT_DISCLOSED = "not_disclosed"
    UNKNOWN = "unknown"


class EvidenceScope(StrEnum):
    PRODUCT = "product"
    BRAND = "brand"


class AssessmentSourceRead(BaseModel):
    title: str
    provider_name: str
    url: str
    published_at: datetime | None
    source_location: str | None


class ConsumerAssessment(BaseModel):
    dimension: AssessmentDimension
    title: str
    status: AssessmentStatus
    finding: str
    evidence_scope: EvidenceScope
    sources: list[AssessmentSourceRead] = Field(default_factory=list)


class ConsumerProductRead(BaseModel):
    barcode: str
    name: str
    brand: str | None
    image_url: str | None
    source_url: str
    source_name: str
    last_updated_at: datetime | None
    evidence_coverage_percent: int = Field(ge=0, le=100)
    assessments: list[ConsumerAssessment]


class ConsumerSearchResponse(BaseModel):
    query: str
    query_type: SearchQueryType
    items: list[ConsumerProductRead]
    total: int
    disclaimer: str
