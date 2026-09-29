from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, StringConstraints, model_validator


class SearchQueryType(StrEnum):
    BARCODE = "barcode"
    TEXT = "text"


class AssessmentDimension(StrEnum):
    VEGAN_COMPOSITION = "vegan_composition"
    ENVIRONMENTAL_IMPACT = "environmental_impact"
    WOMEN_WORKERS = "women_workers"
    MINORITY_INCLUSION = "minority_inclusion"


class FoodCategory(StrEnum):
    BABY_FOOD = "baby_food"
    BAKERY = "bakery"
    BEVERAGES = "beverages"
    BISCUITS_COOKIES = "biscuits_cookies"
    BREAKFAST_CEREALS = "breakfast_cereals"
    CANDY = "candy"
    CHOCOLATE = "chocolate"
    COFFEE_TEA = "coffee_tea"
    CONDIMENTS_SAUCES = "condiments_sauces"
    DAIRY = "dairy"
    DAIRY_ALTERNATIVES = "dairy_alternatives"
    DESSERTS = "desserts"
    FROZEN_FOODS = "frozen_foods"
    ICE_CREAM = "ice_cream"
    MEAT_ALTERNATIVES = "meat_alternatives"
    PASTA_NOODLES = "pasta_noodles"
    READY_MEALS = "ready_meals"
    SNACKS_CHIPS = "snacks_chips"
    SPREADS = "spreads"
    YOGURT = "yogurt"
    OTHER = "other"


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


class CommunityReportStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    PUBLISHED_UNVERIFIED = "published_unverified"
    REJECTED = "rejected"


class CommunityReportOutcome(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class CommunityReportAssessment(BaseModel):
    dimension: AssessmentDimension
    outcome: CommunityReportOutcome


class CommunityReportCreate(BaseModel):
    product_name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=300),
    ] = None
    barcode: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, pattern=r"^\d{8,14}$"),
    ] = None
    category: FoodCategory
    assessments: list[CommunityReportAssessment] = Field(min_length=1, max_length=4)
    details: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=10, max_length=1500),
    ]
    evidence_url: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> CommunityReportCreate:
        if self.product_name is None and self.barcode is None:
            raise ValueError("Provide a product name or barcode.")
        dimensions = [assessment.dimension for assessment in self.assessments]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("Report each assessment dimension only once.")
        return self


class CommunityReportRead(BaseModel):
    id: UUID
    product_name: str | None
    barcode: str | None
    category: FoodCategory
    assessments: list[CommunityReportAssessment]
    status: CommunityReportStatus
    has_photo: bool
    document_count: int
    submitted_at: datetime
    notice: str


class CommunityReportAttachmentRead(BaseModel):
    id: UUID
    file_name: str
    mime_type: str
    download_url: str


class PublicCommunityReportRead(BaseModel):
    id: UUID
    product_name: str | None
    barcode: str | None
    category: FoodCategory
    assessments: list[CommunityReportAssessment]
    observations: str
    evidence_url: str | None
    photo_url: str | None
    documents: list[CommunityReportAttachmentRead]
    status: Literal["published_unverified"] = "published_unverified"
    published_at: datetime


class PublicCommunityReportList(BaseModel):
    items: list[PublicCommunityReportRead]
    total: int
    disclaimer: str


class CommunityReportOutcomeCounts(BaseModel):
    positive: int = 0
    negative: int = 0


class CommunityReportSummary(BaseModel):
    total: int = 0
    pending_review: int = 0
    assessment_counts: dict[AssessmentDimension, CommunityReportOutcomeCounts] = Field(
        default_factory=dict
    )


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
    legal_entity: str | None = None
    parent_company: str | None = None
    jurisdiction: str | None = None
    entity_source_url: str | None = None


class ConsumerProductRead(BaseModel):
    barcode: str | None
    name: str
    brand: str | None
    category: FoodCategory | None = None
    catalog_product: bool = True
    image_url: str | None
    source_url: str
    source_name: str
    last_updated_at: datetime | None
    evidence_coverage_percent: int = Field(ge=0, le=100)
    assessments: list[ConsumerAssessment]
    research: ProductResearchMetadata | None = None
    community_reports: CommunityReportSummary = Field(default_factory=CommunityReportSummary)


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


class OrganizationResolution(BaseModel):
    legal_name: str | None = Field(default=None, max_length=300)
    parent_company: str | None = Field(default=None, max_length=300)
    jurisdiction: str | None = Field(default=None, max_length=200)
    source_numbers: list[int] = Field(default_factory=list, max_length=8)


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
    organization: OrganizationResolution | None = None


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
    cached: bool = False


class GroundedAnswerOutput(BaseModel):
    answer: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
    ]
    cited_evidence_numbers: list[int] = Field(default_factory=list, max_length=8)
    insufficient_evidence: bool


ResearchOrigin = Literal["catalog", "ai_research"]
