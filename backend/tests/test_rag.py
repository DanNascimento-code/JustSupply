from uuid import UUID

from fastapi.testclient import TestClient

from justsupply.dependencies import get_rag_service
from justsupply.domain.rag import GeneratedAnswer, RetrievedChunk
from justsupply.evaluation.retrieval import (
    aggregate_retrieval_metrics,
    evaluate_retrieval_case,
)
from justsupply.main import app
from justsupply.schemas.rag import (
    DocumentIndexResponse,
    RagAnswerResponse,
    RagCitation,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResponse,
)
from justsupply.services.rag import RagService
from justsupply.services.text_chunking import chunk_document

BRAND_ID = UUID("c65e471a-8e8e-4d89-a493-99d04b56154f")
DOCUMENT_ID = UUID("ad637cba-4450-4b8f-8798-902a34783bd2")
CHUNK_ID = UUID("77075032-6088-4b20-9d6d-ff250395518d")


def retrieved_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        id=CHUNK_ID,
        document_id=DOCUMENT_ID,
        text="Women represented 48 percent of program participants.",
        chunk_index=0,
        page_number=12,
        character_start=0,
        character_end=52,
        source_title="2025 Impact Report",
        source_provider="Example Organization",
        source_url="https://example.org/report",
        filename="report.pdf",
        similarity=0.91,
    )


class StubRagService:
    retrieval_model = "test-embedding-model"

    def ask(self, brand_id: UUID, question: str, *, top_k: int) -> RagAnswerResponse:
        assert brand_id == BRAND_ID
        assert top_k == 3
        return RagAnswerResponse(
            question=question,
            answer="The report documents participation by women. [1]",
            insufficient_evidence=False,
            citations=[
                RagCitation(
                    number=1,
                    chunk_id=CHUNK_ID,
                    document_id=DOCUMENT_ID,
                    source_title="2025 Impact Report",
                    source_provider="Example Organization",
                    source_url="https://example.org/report",
                    filename="report.pdf",
                    source_location="page 12",
                    excerpt="Women represented 48 percent of program participants.",
                    similarity=0.91,
                )
            ],
            retrieval_model=self.retrieval_model,
            generation_model="test-generation-model",
            prompt_version="grounded-rag-v1",
        )

    def index_document(self, document_id: UUID) -> int:
        assert document_id == DOCUMENT_ID
        return 3

    def evaluate(
        self,
        brand_id: UUID,
        request: RetrievalEvaluationRequest,
    ) -> RetrievalEvaluationResponse:
        assert brand_id == BRAND_ID
        assert request.top_k == 3
        return RetrievalEvaluationResponse(
            top_k=3,
            case_count=1,
            hit_rate=1.0,
            mean_reciprocal_rank=1.0,
            mean_precision=1.0,
            mean_recall=1.0,
            cases=[],
        )


def test_rag_routes_ask_index_and_evaluate(client: TestClient) -> None:
    app.dependency_overrides[get_rag_service] = lambda: StubRagService()

    ask_response = client.post(
        f"/api/v1/rag/brands/{BRAND_ID}/ask",
        json={"question": "What does the report say about women workers?", "top_k": 3},
    )
    index_response = client.post(f"/api/v1/rag/documents/{DOCUMENT_ID}/index")
    evaluation_response = client.post(
        f"/api/v1/rag/brands/{BRAND_ID}/evaluations",
        json={
            "top_k": 3,
            "cases": [
                {
                    "question": "What does the report say about women workers?",
                    "relevant_document_ids": [str(DOCUMENT_ID)],
                }
            ],
        },
    )

    assert ask_response.status_code == 200
    assert ask_response.json()["citations"][0]["source_location"] == "page 12"
    assert index_response.status_code == 200
    assert DocumentIndexResponse.model_validate(index_response.json()).chunk_count == 3
    assert evaluation_response.status_code == 200
    assert evaluation_response.json()["hit_rate"] == 1.0


def test_chunker_preserves_pdf_page_locations_and_overlap() -> None:
    text = "[Page 1]\n" + ("alpha evidence sentence. " * 20)
    text += "\n\n[Page 2]\n" + ("beta evidence sentence. " * 20)

    chunks = chunk_document(
        text,
        target_characters=180,
        overlap_characters=40,
    )

    assert len(chunks) > 2
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.text) <= 180 for chunk in chunks)


def test_retrieval_metrics_report_hit_rate_and_mrr() -> None:
    other_document_id = UUID("7c4ecbf5-425d-4bd8-b718-999a07522a84")
    hit = evaluate_retrieval_case(
        [other_document_id, DOCUMENT_ID],
        {DOCUMENT_ID},
    )
    miss = evaluate_retrieval_case([other_document_id], {DOCUMENT_ID})
    aggregate = aggregate_retrieval_metrics([hit, miss])

    assert hit.first_relevant_rank == 2
    assert hit.reciprocal_rank == 0.5
    assert miss.hit is False
    assert aggregate.hit_rate == 0.5
    assert aggregate.mean_reciprocal_rank == 0.25
    assert hit.precision == 0.5
    assert hit.recall == 1.0
    assert aggregate.mean_precision == 0.25
    assert aggregate.mean_recall == 0.5


def test_rag_service_discards_citations_outside_retrieved_context() -> None:
    class FakeRetriever:
        model_name = "test-embedding-model"

    class FakeOrchestrator:
        generation_model = "test-generation-model"
        prompt_version = "grounded-rag-v1"

        def answer(
            self,
            brand_id: UUID,
            question: str,
            *,
            top_k: int,
        ) -> tuple[GeneratedAnswer, list[RetrievedChunk]]:
            del brand_id, question, top_k
            return (
                GeneratedAnswer(
                    answer="Supported statement [1] and invented citation [99].",
                    cited_chunk_numbers=[1, 99],
                    insufficient_evidence=False,
                    provider_response_id="resp_test",
                ),
                [retrieved_chunk()],
            )

    service = RagService(
        repository=object(),  # type: ignore[arg-type]
        retriever=FakeRetriever(),  # type: ignore[arg-type]
        orchestrator=FakeOrchestrator(),  # type: ignore[arg-type]
        indexer=object(),  # type: ignore[arg-type]
    )

    response = service.ask(BRAND_ID, "Question", top_k=5)

    assert response.insufficient_evidence is False
    assert len(response.citations) == 1
    assert "[99]" not in response.answer
    assert response.citations[0].chunk_id == CHUNK_ID
