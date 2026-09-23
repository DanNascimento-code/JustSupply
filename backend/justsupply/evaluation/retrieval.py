from collections.abc import Hashable
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCaseMetrics:
    first_relevant_rank: int | None
    hit: bool
    reciprocal_rank: float
    precision: float
    recall: float


@dataclass(frozen=True)
class RetrievalAggregateMetrics:
    hit_rate: float
    mean_reciprocal_rank: float
    mean_precision: float
    mean_recall: float


def evaluate_retrieval_case[DocumentId: Hashable](
    retrieved_document_ids: list[DocumentId],
    relevant_document_ids: set[DocumentId],
) -> RetrievalCaseMetrics:
    if not relevant_document_ids:
        raise ValueError("At least one relevant document is required.")
    first_relevant_rank = next(
        (
            rank
            for rank, document_id in enumerate(retrieved_document_ids, start=1)
            if document_id in relevant_document_ids
        ),
        None,
    )
    relevant_retrieved = len(set(retrieved_document_ids) & relevant_document_ids)
    return RetrievalCaseMetrics(
        first_relevant_rank=first_relevant_rank,
        hit=first_relevant_rank is not None,
        reciprocal_rank=(1 / first_relevant_rank if first_relevant_rank is not None else 0.0),
        precision=(
            relevant_retrieved / len(retrieved_document_ids) if retrieved_document_ids else 0.0
        ),
        recall=relevant_retrieved / len(relevant_document_ids),
    )


def aggregate_retrieval_metrics(
    cases: list[RetrievalCaseMetrics],
) -> RetrievalAggregateMetrics:
    if not cases:
        raise ValueError("At least one evaluation case is required.")
    return RetrievalAggregateMetrics(
        hit_rate=sum(case.hit for case in cases) / len(cases),
        mean_reciprocal_rank=sum(case.reciprocal_rank for case in cases) / len(cases),
        mean_precision=sum(case.precision for case in cases) / len(cases),
        mean_recall=sum(case.recall for case in cases) / len(cases),
    )
