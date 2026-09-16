from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievalCaseMetrics:
    first_relevant_rank: int | None
    hit: bool
    reciprocal_rank: float


@dataclass(frozen=True)
class RetrievalAggregateMetrics:
    hit_rate: float
    mean_reciprocal_rank: float


def evaluate_retrieval_case(
    retrieved_document_ids: list[UUID],
    relevant_document_ids: set[UUID],
) -> RetrievalCaseMetrics:
    first_relevant_rank = next(
        (
            rank
            for rank, document_id in enumerate(retrieved_document_ids, start=1)
            if document_id in relevant_document_ids
        ),
        None,
    )
    return RetrievalCaseMetrics(
        first_relevant_rank=first_relevant_rank,
        hit=first_relevant_rank is not None,
        reciprocal_rank=(1 / first_relevant_rank if first_relevant_rank is not None else 0.0),
    )


def aggregate_retrieval_metrics(
    cases: list[RetrievalCaseMetrics],
) -> RetrievalAggregateMetrics:
    if not cases:
        raise ValueError("At least one evaluation case is required.")
    return RetrievalAggregateMetrics(
        hit_rate=sum(case.hit for case in cases) / len(cases),
        mean_reciprocal_rank=sum(case.reciprocal_rank for case in cases) / len(cases),
    )
