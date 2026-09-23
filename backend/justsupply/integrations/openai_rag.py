from openai import OpenAI, OpenAIError

from justsupply.domain.rag import GeneratedAnswer, RetrievedChunk
from justsupply.integrations.ai import (
    GROUNDING_INSTRUCTIONS,
    RAG_PROMPT_VERSION,
    format_evidence_context,
)
from justsupply.schemas.rag import GroundedAnswerOutput
from justsupply.services.rag import RagProviderError


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model_name: str, dimensions: int) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self._client = OpenAI(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        embeddings = self._embed([text])
        if len(embeddings) != 1:
            raise RagProviderError("The embedding service returned an unexpected result count.")
        return embeddings[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(
                model=self.model_name,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except OpenAIError as error:
            raise RagProviderError("The embedding service is temporarily unavailable.") from error

        ordered = sorted(response.data, key=lambda item: item.index)
        embeddings = [item.embedding for item in ordered]
        if any(len(embedding) != self.dimensions for embedding in embeddings):
            raise RagProviderError("The embedding service returned an unexpected vector size.")
        return embeddings


class OpenAIGroundedAnswerGenerator:
    prompt_version = RAG_PROMPT_VERSION

    def __init__(self, api_key: str, model_name: str) -> None:
        self.model_name = model_name
        self._client = OpenAI(api_key=api_key)

    def generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> GeneratedAnswer:
        context = format_evidence_context(chunks)
        try:
            response = self._client.responses.parse(
                model=self.model_name,
                instructions=GROUNDING_INSTRUCTIONS,
                input=(
                    f"<question>\n{question}\n</question>\n\n"
                    f"<retrieved_evidence>\n{context}\n</retrieved_evidence>"
                ),
                text_format=GroundedAnswerOutput,
                max_output_tokens=1800,
                store=False,
            )
        except OpenAIError as error:
            raise RagProviderError(
                "The grounded answer service is temporarily unavailable."
            ) from error

        parsed = response.output_parsed
        if parsed is None:
            raise RagProviderError("The AI service did not return a valid grounded answer.")
        return GeneratedAnswer(
            answer=parsed.answer,
            cited_chunk_numbers=parsed.cited_chunk_numbers,
            insufficient_evidence=parsed.insufficient_evidence,
            provider_response_id=response.id,
        )
