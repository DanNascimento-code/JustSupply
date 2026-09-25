from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints


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


class VerificationLevel(StrEnum):
    CATALOG_DATA = "catalog_data"
    MULTIPLE_SOURCES = "multiple_sources"
    SINGLE_SOURCE = "single_source"
    UNVERIFIED = "unverified"


class UserLocale(StrEnum):
    ENGLISH = "en"
    PORTUGUESE_BRAZIL = "pt-BR"
    SPANISH_LATAM = "es-419"


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
    verification: VerificationLevel
    verification_note: str
    limitations: str | None = None
    sources: list[AssessmentSourceRead] = Field(default_factory=list)


class ProductResearchMetadata(BaseModel):
    researched_at: datetime
    model_name: str
    source_count: int


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
    research: ProductResearchMetadata | None = None


class ConsumerSearchResponse(BaseModel):
    query: str
    query_type: SearchQueryType
    items: list[ConsumerProductRead]
    total: int
    disclaimer: str


class LocalizedAssessmentText(BaseModel):
    finding: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=800),
    ]
    limitations: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
    ] = None


class AiResearchTranslations(BaseModel):
    pt_br: LocalizedAssessmentText
    es_latam: LocalizedAssessmentText


class AiResearchAssessment(BaseModel):
    dimension: AssessmentDimension
    status: AssessmentStatus
    finding: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=800),
    ]
    evidence_scope: EvidenceScope
    source_numbers: list[int] = Field(default_factory=list, max_length=8)
    limitations: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=500),
    ] = None
    translations: AiResearchTranslations


class AiResearchSynthesis(BaseModel):
    assessments: list[AiResearchAssessment] = Field(min_length=4, max_length=4)


class ProductResearchResponse(BaseModel):
    product: ConsumerProductRead
    cached: bool


ConsumerQuestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
]


class ConsumerQuestionRequest(BaseModel):
    question: ConsumerQuestion
    top_k: int = Field(default=4, ge=1, le=8)
    language: UserLocale = UserLocale.ENGLISH


class ConsumerCitation(BaseModel):
    number: int
    evidence_id: UUID
    title: str
    provider_name: str
    url: str
    excerpt: str
    similarity: float


class ConsumerAnswerResponse(BaseModel):
    question: str
    answer: str
    insufficient_evidence: bool
    citations: list[ConsumerCitation]
    retrieval_model: str
    generation_model: str
    prompt_version: str


class GroundedAnswerOutput(BaseModel):
    answer: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
    ]
    cited_evidence_numbers: list[int] = Field(default_factory=list, max_length=8)
    insufficient_evidence: bool


ResearchOrigin = Literal["catalog", "ai_research"]
