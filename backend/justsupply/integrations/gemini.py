from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from justsupply.domain.rag import GeneratedAnswer, RetrievedChunk
from justsupply.integrations.ai import (
    EXTRACTION_INSTRUCTIONS,
    EXTRACTION_PROMPT_VERSION,
    GROUNDING_INSTRUCTIONS,
    RAG_PROMPT_VERSION,
    AiExtractionError,
    format_evidence_context,
)
from justsupply.schemas.document_ingestion import AiExtractionOutput
from justsupply.schemas.rag import GroundedAnswerOutput
from justsupply.services.rag import RagProviderError


class GeminiEvidenceExtractor:
    prompt_version = EXTRACTION_PROMPT_VERSION

    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self._client = client or genai.Client(api_key=api_key)

    def extract(self, brand_name: str, document_text: str) -> tuple[str | None, AiExtractionOutput]:
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=(
                    f"Brand under review: {brand_name}\n\n"
                    "Extract reviewable findings from the document below.\n\n"
                    f"<document>\n{document_text}\n</document>"
                ),
                config=types.GenerateContentConfig(
                    system_instruction=EXTRACTION_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_schema=AiExtractionOutput,
                    max_output_tokens=3000,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            parsed = _validate_response(response, AiExtractionOutput)
        except errors.APIError as error:
            raise AiExtractionError(
                "The AI extraction service is temporarily unavailable."
            ) from error
        except (TypeError, ValueError, ValidationError) as error:
            raise AiExtractionError(
                "The AI service did not return a valid structured extraction."
            ) from error

        return _response_id(response), parsed


class GeminiEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        dimensions: int,
        *,
        client: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self._client = client or genai.Client(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prepared = [f"title: none | text: {text}" for text in texts]
        return self._embed(prepared)

    def embed_query(self, text: str) -> list[float]:
        embeddings = self._embed([f"task: question answering | query: {text}"])
        if len(embeddings) != 1:
            raise RagProviderError("The embedding service returned an unexpected result count.")
        return embeddings[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        contents = [types.Content(parts=[types.Part(text=text)], role="user") for text in texts]
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=self.dimensions),
            )
        except errors.APIError as error:
            raise RagProviderError("The embedding service is temporarily unavailable.") from error

        embeddings = [list(item.values or []) for item in response.embeddings or []]
        if len(embeddings) != len(texts):
            raise RagProviderError("The embedding service returned an unexpected result count.")
        if any(len(embedding) != self.dimensions for embedding in embeddings):
            raise RagProviderError("The embedding service returned an unexpected vector size.")
        return embeddings


class GeminiGroundedAnswerGenerator:
    prompt_version = RAG_PROMPT_VERSION

    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self._client = client or genai.Client(api_key=api_key)

    def generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> GeneratedAnswer:
        context = format_evidence_context(chunks)
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=(
                    f"<question>\n{question}\n</question>\n\n"
                    f"<retrieved_evidence>\n{context}\n</retrieved_evidence>"
                ),
                config=types.GenerateContentConfig(
                    system_instruction=GROUNDING_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_schema=GroundedAnswerOutput,
                    max_output_tokens=1800,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            parsed = _validate_response(response, GroundedAnswerOutput)
        except errors.APIError as error:
            raise RagProviderError(
                "The grounded answer service is temporarily unavailable."
            ) from error
        except (TypeError, ValueError, ValidationError) as error:
            raise RagProviderError(
                "The AI service did not return a valid grounded answer."
            ) from error

        return GeneratedAnswer(
            answer=parsed.answer,
            cited_chunk_numbers=parsed.cited_chunk_numbers,
            insufficient_evidence=parsed.insufficient_evidence,
            provider_response_id=_response_id(response),
        )


def _validate_response(response: Any, schema: type[Any]) -> Any:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    text = getattr(response, "text", None)
    if not text:
        raise ValueError("The provider response did not contain structured text.")
    return schema.model_validate_json(text)


def _response_id(response: Any) -> str | None:
    value = getattr(response, "response_id", None)
    return value if isinstance(value, str) and value else None
