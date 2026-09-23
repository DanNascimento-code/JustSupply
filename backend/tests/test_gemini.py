from types import SimpleNamespace
from uuid import UUID

import pytest

from justsupply.core.config import Settings
from justsupply.domain.rag import RetrievedChunk
from justsupply.integrations.gemini import (
    GeminiEmbeddingProvider,
    GeminiEvidenceExtractor,
    GeminiGroundedAnswerGenerator,
)
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus


class FakeGeminiModels:
    def __init__(self) -> None:
        self.generation_responses: list[object] = []
        self.embedding_inputs: list[list[object]] = []

    def generate_content(self, **kwargs: object) -> object:
        del kwargs
        return self.generation_responses.pop(0)

    def embed_content(self, **kwargs: object) -> object:
        contents = kwargs["contents"]
        assert isinstance(contents, list)
        self.embedding_inputs.append(contents)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.25] * 1536) for _ in contents])


class FakeGeminiClient:
    def __init__(self) -> None:
        self.models = FakeGeminiModels()


def test_settings_accepts_standard_gemini_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.ai_provider == "gemini"
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "test-secret"


def test_gemini_extractor_uses_validated_structured_output() -> None:
    client = FakeGeminiClient()
    client.models.generation_responses.append(
        SimpleNamespace(
            response_id="gemini-extraction-1",
            parsed=None,
            text=(
                '{"findings":[{"dimension":"women_workers","status":"supported",'
                '"statement":"Women participated in training.",'
                '"excerpt":"Women participated in training.",'
                '"source_location":"page 2","rationale":"Direct statement."}]}'
            ),
        )
    )
    extractor = GeminiEvidenceExtractor(
        "unused-test-key",
        "gemini-test",
        client=client,
    )

    response_id, extraction = extractor.extract(
        "Example Brand",
        "Women participated in training.",
    )

    assert response_id == "gemini-extraction-1"
    assert extraction.findings[0].dimension == AssessmentDimension.WOMEN_WORKERS
    assert extraction.findings[0].status == AssessmentStatus.SUPPORTED


def test_gemini_embeddings_keep_document_and_query_requests_separate() -> None:
    client = FakeGeminiClient()
    provider = GeminiEmbeddingProvider(
        "unused-test-key",
        "gemini-embedding-test",
        1536,
        client=client,
    )

    document_embeddings = provider.embed_documents(["first chunk", "second chunk"])
    query_embedding = provider.embed_query("What evidence exists?")

    assert len(document_embeddings) == 2
    assert len(document_embeddings[0]) == 1536
    assert len(query_embedding) == 1536
    assert len(client.models.embedding_inputs) == 2


def test_gemini_grounded_answer_maps_structured_output() -> None:
    client = FakeGeminiClient()
    client.models.generation_responses.append(
        SimpleNamespace(
            response_id="gemini-answer-1",
            parsed=None,
            text=(
                '{"answer":"The report documents participation by women. [1]",'
                '"cited_chunk_numbers":[1],"insufficient_evidence":false}'
            ),
        )
    )
    generator = GeminiGroundedAnswerGenerator(
        "unused-test-key",
        "gemini-test",
        client=client,
    )
    chunk = RetrievedChunk(
        id=UUID("77075032-6088-4b20-9d6d-ff250395518d"),
        document_id=UUID("ad637cba-4450-4b8f-8798-902a34783bd2"),
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

    generated = generator.generate("What does the report say?", [chunk])

    assert generated.provider_response_id == "gemini-answer-1"
    assert generated.cited_chunk_numbers == [1]
    assert generated.insufficient_evidence is False
