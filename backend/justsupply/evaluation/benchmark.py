import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from justsupply.evaluation.retrieval import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_case,
)
from justsupply.services.rag import EmbeddingProvider, RagProviderError
from justsupply.services.text_chunking import chunk_document

BenchmarkId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=3, max_length=80),
]


class BenchmarkDocument(BaseModel):
    id: BenchmarkId
    title: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=80)


class BenchmarkCase(BaseModel):
    id: BenchmarkId
    question: str = Field(min_length=3, max_length=500)
    relevant_document_ids: set[BenchmarkId] = Field(min_length=1)


class RetrievalBenchmark(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    version: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=10, max_length=1000)
    documents: list[BenchmarkDocument] = Field(min_length=2)
    cases: list[BenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identifiers(self) -> Self:
        document_ids = [document.id for document in self.documents]
        case_ids = [case.id for case in self.cases]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("Benchmark document identifiers must be unique.")
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Benchmark case identifiers must be unique.")

        known_documents = set(document_ids)
        unknown_references = {
            document_id
            for case in self.cases
            for document_id in case.relevant_document_ids
            if document_id not in known_documents
        }
        if unknown_references:
            unknown = ", ".join(sorted(unknown_references))
            raise ValueError(f"Benchmark cases reference unknown documents: {unknown}.")
        return self


class BenchmarkCaseResult(BaseModel):
    case_id: str
    question: str
    relevant_document_ids: list[str]
    retrieved_document_ids: list[str]
    first_relevant_rank: int | None
    hit: bool
    reciprocal_rank: float
    precision: float
    recall: float


class BenchmarkTopKResult(BaseModel):
    top_k: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_precision: float
    mean_recall: float
    cases: list[BenchmarkCaseResult]


class BenchmarkReport(BaseModel):
    benchmark_name: str
    benchmark_version: str
    benchmark_sha256: str
    created_at: datetime
    embedding_model: str
    embedding_dimensions: int
    target_characters: int
    overlap_characters: int
    document_count: int
    chunk_count: int
    case_count: int
    results: list[BenchmarkTopKResult]


@dataclass(frozen=True)
class _EmbeddedChunk:
    document_id: str
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class _CaseRanking:
    case: BenchmarkCase
    ranked_chunk_document_ids: list[str]


def load_benchmark(path: Path) -> RetrievalBenchmark:
    return RetrievalBenchmark.model_validate_json(path.read_text(encoding="utf-8"))


class RetrievalBenchmarkRunner:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        target_characters: int,
        overlap_characters: int,
    ) -> None:
        if target_characters < 100:
            raise ValueError("target_characters must be at least 100.")
        if overlap_characters < 0 or overlap_characters >= target_characters:
            raise ValueError("overlap_characters must be between zero and the target size.")
        self._embedding_provider = embedding_provider
        self._target_characters = target_characters
        self._overlap_characters = overlap_characters

    def run(self, benchmark: RetrievalBenchmark, *, top_ks: list[int]) -> BenchmarkReport:
        normalized_top_ks = sorted(set(top_ks))
        if not normalized_top_ks or normalized_top_ks[0] < 1:
            raise ValueError("At least one positive top_k value is required.")

        chunks = self._embed_corpus(benchmark)
        rankings = [
            self._rank_case(case, chunks, max_top_k=normalized_top_ks[-1])
            for case in benchmark.cases
        ]
        results = [self._evaluate(rankings, top_k=top_k) for top_k in normalized_top_ks]
        benchmark_json = _canonical_benchmark_json(benchmark)
        return BenchmarkReport(
            benchmark_name=benchmark.name,
            benchmark_version=benchmark.version,
            benchmark_sha256=sha256(benchmark_json.encode("utf-8")).hexdigest(),
            created_at=datetime.now(UTC),
            embedding_model=self._embedding_provider.model_name,
            embedding_dimensions=self._embedding_provider.dimensions,
            target_characters=self._target_characters,
            overlap_characters=self._overlap_characters,
            document_count=len(benchmark.documents),
            chunk_count=len(chunks),
            case_count=len(benchmark.cases),
            results=results,
        )

    def _embed_corpus(self, benchmark: RetrievalBenchmark) -> list[_EmbeddedChunk]:
        pending: list[tuple[str, str]] = []
        for document in benchmark.documents:
            document_chunks = chunk_document(
                document.text,
                target_characters=self._target_characters,
                overlap_characters=self._overlap_characters,
            )
            pending.extend((document.id, chunk.text) for chunk in document_chunks)

        embeddings = self._embedding_provider.embed_documents([text for _, text in pending])
        if len(embeddings) != len(pending):
            raise RagProviderError("The benchmark embedding count did not match its chunks.")
        return [
            _EmbeddedChunk(document_id=document_id, text=text, embedding=embedding)
            for (document_id, text), embedding in zip(pending, embeddings, strict=True)
        ]

    def _rank_case(
        self,
        case: BenchmarkCase,
        chunks: list[_EmbeddedChunk],
        *,
        max_top_k: int,
    ) -> _CaseRanking:
        query_embedding = self._embedding_provider.embed_query(case.question)
        ranked_chunks = sorted(
            chunks,
            key=lambda chunk: _cosine_similarity(query_embedding, chunk.embedding),
            reverse=True,
        )[:max_top_k]
        return _CaseRanking(
            case=case,
            ranked_chunk_document_ids=[chunk.document_id for chunk in ranked_chunks],
        )

    def _evaluate(
        self,
        rankings: list[_CaseRanking],
        *,
        top_k: int,
    ) -> BenchmarkTopKResult:
        results: list[BenchmarkCaseResult] = []
        metrics = []
        for ranking in rankings:
            retrieved = list(dict.fromkeys(ranking.ranked_chunk_document_ids[:top_k]))
            case_metrics = evaluate_retrieval_case(
                retrieved,
                ranking.case.relevant_document_ids,
            )
            metrics.append(case_metrics)
            results.append(
                BenchmarkCaseResult(
                    case_id=ranking.case.id,
                    question=ranking.case.question,
                    relevant_document_ids=sorted(ranking.case.relevant_document_ids),
                    retrieved_document_ids=retrieved,
                    first_relevant_rank=case_metrics.first_relevant_rank,
                    hit=case_metrics.hit,
                    reciprocal_rank=case_metrics.reciprocal_rank,
                    precision=case_metrics.precision,
                    recall=case_metrics.recall,
                )
            )

        aggregate = aggregate_retrieval_metrics(metrics)
        return BenchmarkTopKResult(
            top_k=top_k,
            hit_rate=aggregate.hit_rate,
            mean_reciprocal_rank=aggregate.mean_reciprocal_rank,
            mean_precision=aggregate.mean_precision,
            mean_recall=aggregate.mean_recall,
            cases=results,
        )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise RagProviderError("Cannot compare embeddings with different dimensions.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _canonical_benchmark_json(benchmark: RetrievalBenchmark) -> str:
    payload = benchmark.model_dump(mode="json")
    for case in payload["cases"]:
        case["relevant_document_ids"] = sorted(case["relevant_document_ids"])
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
