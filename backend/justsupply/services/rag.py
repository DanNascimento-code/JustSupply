import re
from typing import Protocol
from uuid import UUID

from justsupply.domain.rag import GeneratedAnswer, IndexedChunk, RetrievedChunk
from justsupply.evaluation.retrieval import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_case,
)
from justsupply.repositories.rag import SqlAlchemyRagRepository
from justsupply.schemas.rag import (
    RagAnswerResponse,
    RagCitation,
    RetrievalEvaluationCaseResult,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResponse,
)
from justsupply.services.text_chunking import chunk_document


class RagProviderError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        pass

    def embed_query(self, text: str) -> list[float]:
        pass


class AnswerGenerator(Protocol):
    model_name: str
    prompt_version: str

    def generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> GeneratedAnswer:
        pass


class RagOrchestrator(Protocol):
    generation_model: str
    prompt_version: str

    def answer(
        self,
        brand_id: UUID,
        question: str,
        *,
        top_k: int,
    ) -> tuple[GeneratedAnswer, list[RetrievedChunk]]:
        pass


class RagIndexingService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        target_characters: int,
        overlap_characters: int,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._target_characters = target_characters
        self._overlap_characters = overlap_characters

    @property
    def embedding_model(self) -> str:
        return self._embedding_provider.model_name

    @property
    def embedding_dimensions(self) -> int:
        return self._embedding_provider.dimensions

    def prepare(self, text: str) -> list[IndexedChunk]:
        chunks = chunk_document(
            text,
            target_characters=self._target_characters,
            overlap_characters=self._overlap_characters,
        )
        if not chunks:
            return []
        embeddings = self._embedding_provider.embed_documents([chunk.text for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise RagProviderError("The embedding service returned an unexpected result count.")
        return [
            IndexedChunk(chunk=chunk, embedding=embedding)
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]


class RagRetriever:
    def __init__(
        self,
        repository: SqlAlchemyRagRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider

    @property
    def model_name(self) -> str:
        return self._embedding_provider.model_name

    def retrieve(
        self,
        brand_id: UUID,
        question: str,
        *,
        top_k: int,
    ) -> list[RetrievedChunk]:
        embedding = self._embedding_provider.embed_query(question)
        return self._repository.search(
            brand_id,
            embedding,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimensions=self._embedding_provider.dimensions,
            top_k=top_k,
        )


class RagService:
    def __init__(
        self,
        repository: SqlAlchemyRagRepository,
        retriever: RagRetriever,
        orchestrator: RagOrchestrator,
        indexer: RagIndexingService,
    ) -> None:
        self._repository = repository
        self._retriever = retriever
        self._orchestrator = orchestrator
        self._indexer = indexer

    @property
    def retrieval_model(self) -> str:
        return self._retriever.model_name

    def ask(self, brand_id: UUID, question: str, *, top_k: int) -> RagAnswerResponse:
        generated, chunks = self._orchestrator.answer(
            brand_id,
            question,
            top_k=top_k,
        )
        if not chunks or generated.insufficient_evidence:
            return self._insufficient_answer(question)

        valid_numbers = _valid_citation_numbers(
            generated.cited_chunk_numbers,
            chunk_count=len(chunks),
        )
        if not valid_numbers:
            return self._insufficient_answer(question)

        answer = _remove_invalid_citation_markers(generated.answer, set(valid_numbers))
        missing_markers = [number for number in valid_numbers if f"[{number}]" not in answer]
        if missing_markers:
            markers = " ".join(f"[{number}]" for number in missing_markers)
            answer = f"{answer.rstrip()} {markers}"

        citations = [_to_citation(number, chunks[number - 1]) for number in valid_numbers]
        return RagAnswerResponse(
            question=question,
            answer=answer,
            insufficient_evidence=False,
            citations=citations,
            retrieval_model=self._retriever.model_name,
            generation_model=self._orchestrator.generation_model,
            prompt_version=self._orchestrator.prompt_version,
        )

    def index_document(self, document_id: UUID) -> int:
        document = self._repository.get_document_for_indexing(document_id)
        chunks = self._indexer.prepare(document.text)
        return self._repository.replace_chunks(
            document.id,
            chunks,
            embedding_model=self._indexer.embedding_model,
            embedding_dimensions=self._indexer.embedding_dimensions,
        )

    def evaluate(
        self,
        brand_id: UUID,
        request: RetrievalEvaluationRequest,
    ) -> RetrievalEvaluationResponse:
        results: list[RetrievalEvaluationCaseResult] = []
        metrics = []
        for case in request.cases:
            chunks = self._retriever.retrieve(
                brand_id,
                case.question,
                top_k=request.top_k,
            )
            document_ids = list(dict.fromkeys(chunk.document_id for chunk in chunks))
            case_metrics = evaluate_retrieval_case(
                document_ids,
                case.relevant_document_ids,
            )
            metrics.append(case_metrics)
            results.append(
                RetrievalEvaluationCaseResult(
                    question=case.question,
                    retrieved_document_ids=document_ids,
                    first_relevant_rank=case_metrics.first_relevant_rank,
                    hit=case_metrics.hit,
                    reciprocal_rank=case_metrics.reciprocal_rank,
                    precision=case_metrics.precision,
                    recall=case_metrics.recall,
                )
            )
        aggregate = aggregate_retrieval_metrics(metrics)
        return RetrievalEvaluationResponse(
            top_k=request.top_k,
            case_count=len(results),
            hit_rate=aggregate.hit_rate,
            mean_reciprocal_rank=aggregate.mean_reciprocal_rank,
            mean_precision=aggregate.mean_precision,
            mean_recall=aggregate.mean_recall,
            cases=results,
        )

    def _insufficient_answer(self, question: str) -> RagAnswerResponse:
        return RagAnswerResponse(
            question=question,
            answer=(
                "The indexed documents do not provide enough evidence to answer this "
                "question. Add a relevant source or ask a narrower question."
            ),
            insufficient_evidence=True,
            citations=[],
            retrieval_model=self._retriever.model_name,
            generation_model=self._orchestrator.generation_model,
            prompt_version=self._orchestrator.prompt_version,
        )


def _valid_citation_numbers(numbers: list[int], *, chunk_count: int) -> list[int]:
    return list(dict.fromkeys(number for number in numbers if 1 <= number <= chunk_count))


def _remove_invalid_citation_markers(answer: str, valid_numbers: set[int]) -> str:
    return re.sub(
        r"\[(\d+)\]",
        lambda match: match.group(0) if int(match.group(1)) in valid_numbers else "",
        answer,
    ).strip()


def _to_citation(number: int, chunk: RetrievedChunk) -> RagCitation:
    return RagCitation(
        number=number,
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        source_title=chunk.source_title,
        source_provider=chunk.source_provider,
        source_url=chunk.source_url,
        filename=chunk.filename,
        source_location=chunk.source_location,
        excerpt=chunk.text,
        similarity=round(chunk.similarity, 4),
    )
