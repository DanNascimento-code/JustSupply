from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from justsupply.schemas.consumer import AiResearchAssessment


@dataclass(frozen=True)
class GroundedWebSource:
    number: int
    title: str
    provider_name: str
    url: str
    cited_text: str


@dataclass(frozen=True)
class AiResearchResult:
    provider_response_id: str | None
    searched_at: datetime
    sources: list[GroundedWebSource]
    assessments: list[AiResearchAssessment]


@dataclass(frozen=True)
class RetrievedEvidence:
    id: UUID
    text: str
    title: str
    provider_name: str
    url: str
    similarity: float


@dataclass(frozen=True)
class GeneratedConsumerAnswer:
    answer: str
    cited_evidence_numbers: list[int]
    insufficient_evidence: bool
    provider_response_id: str | None = None
