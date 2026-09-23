from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

RagQuestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
]


class RagQuestionRequest(BaseModel):
    question: RagQuestion
    top_k: int = Field(default=3, ge=1, le=8)


class RagCitation(BaseModel):
    number: int
    chunk_id: UUID
    document_id: UUID
    source_title: str
    source_provider: str
    source_url: str
    filename: str
    source_location: str
    excerpt: str
    similarity: float


class RagAnswerResponse(BaseModel):
    question: str
    answer: str
    insufficient_evidence: bool
    citations: list[RagCitation]
    retrieval_model: str
    generation_model: str
    prompt_version: str


class DocumentIndexResponse(BaseModel):
    document_id: UUID
    chunk_count: int
    embedding_model: str


class RetrievalEvaluationCaseInput(BaseModel):
    question: RagQuestion
    relevant_document_ids: set[UUID] = Field(min_length=1)


class RetrievalEvaluationRequest(BaseModel):
    cases: list[RetrievalEvaluationCaseInput] = Field(min_length=1, max_length=20)
    top_k: int = Field(default=3, ge=1, le=8)


class RetrievalEvaluationCaseResult(BaseModel):
    question: str
    retrieved_document_ids: list[UUID]
    first_relevant_rank: int | None
    hit: bool
    reciprocal_rank: float
    precision: float
    recall: float


class RetrievalEvaluationResponse(BaseModel):
    top_k: int
    case_count: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_precision: float
    mean_recall: float
    cases: list[RetrievalEvaluationCaseResult]


class GroundedAnswerOutput(BaseModel):
    answer: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
    ]
    cited_chunk_numbers: list[int] = Field(max_length=8)
    insufficient_evidence: bool
