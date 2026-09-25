from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from justsupply.domain.research import (
    AiResearchResult,
    GeneratedConsumerAnswer,
    GroundedWebSource,
    RetrievedEvidence,
)
from justsupply.integrations.ai import (
    ANSWER_INSTRUCTIONS,
    ANSWER_PROMPT_VERSION,
    RESEARCH_INSTRUCTIONS,
    RESEARCH_PROMPT_VERSION,
    SYNTHESIS_INSTRUCTIONS,
    AiResearchError,
    format_evidence_context,
)
from justsupply.schemas.consumer import (
    AiResearchAssessment,
    AiResearchSynthesis,
    AssessmentDimension,
    AssessmentStatus,
    GroundedAnswerOutput,
    LocalizedAssessmentText,
)


class GeminiWebResearcher:
    prompt_version = RESEARCH_PROMPT_VERSION

    def __init__(self, api_key: str, model_name: str, *, client: Any | None = None) -> None:
        self.model_name = model_name
        self._client = client or genai.Client(api_key=api_key)

    def research(self, product_name: str, brand: str | None, barcode: str) -> AiResearchResult:
        identity = f"Product: {product_name}\nBrand: {brand or 'not disclosed'}\nBarcode: {barcode}"
        try:
            grounded_response = self._client.models.generate_content(
                model=self.model_name,
                contents=f"{identity}\n\nResearch this product and brand.",
                config=types.GenerateContentConfig(
                    system_instruction=RESEARCH_INSTRUCTIONS,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    max_output_tokens=5000,
                ),
            )
            grounded_text = _response_text(grounded_response)
            sources = _extract_grounded_sources(grounded_response, grounded_text)
            synthesis_response = self._client.models.generate_content(
                model=self.model_name,
                contents=(
                    f"{identity}\n\n"
                    f"<grounded_research>\n{grounded_text}\n</grounded_research>\n\n"
                    f"<sources>\n{_format_sources(sources)}\n</sources>"
                ),
                config=types.GenerateContentConfig(
                    system_instruction=SYNTHESIS_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_schema=AiResearchSynthesis,
                    max_output_tokens=3500,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            synthesis = _validate_response(synthesis_response, AiResearchSynthesis)
            assessments = _validate_assessments(synthesis.assessments, len(sources))
        except errors.APIError as error:
            raise AiResearchError("Gemini research is temporarily unavailable.") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise AiResearchError("Gemini returned research that could not be verified.") from error

        return AiResearchResult(
            provider_response_id=_response_id(grounded_response),
            searched_at=datetime.now(UTC),
            sources=sources,
            assessments=assessments,
        )


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
        return self._embed([f"title: evidence | text: {text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        embeddings = self._embed([f"task: question answering | query: {text}"])
        if len(embeddings) != 1:
            raise AiResearchError("Gemini returned an unexpected embedding count.")
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
            raise AiResearchError("Gemini embeddings are temporarily unavailable.") from error
        embeddings = [list(item.values or []) for item in response.embeddings or []]
        if len(embeddings) != len(texts) or any(
            len(embedding) != self.dimensions for embedding in embeddings
        ):
            raise AiResearchError("Gemini returned invalid embeddings.")
        return embeddings


class GeminiConsumerAnswerGenerator:
    prompt_version = ANSWER_PROMPT_VERSION

    def __init__(self, api_key: str, model_name: str, *, client: Any | None = None) -> None:
        self.model_name = model_name
        self._client = client or genai.Client(api_key=api_key)

    def generate(
        self,
        question: str,
        evidence: list[RetrievedEvidence],
        language: str,
    ) -> GeneratedConsumerAnswer:
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=(
                    f"<response_language>\n{language}\n</response_language>\n\n"
                    f"<question>\n{question}\n</question>\n\n"
                    f"<retrieved_evidence>\n{format_evidence_context(evidence)}"
                    "\n</retrieved_evidence>"
                ),
                config=types.GenerateContentConfig(
                    system_instruction=ANSWER_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_schema=GroundedAnswerOutput,
                    max_output_tokens=1800,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            parsed = _validate_response(response, GroundedAnswerOutput)
        except errors.APIError as error:
            raise AiResearchError("Gemini answers are temporarily unavailable.") from error
        except (TypeError, ValueError, ValidationError) as error:
            raise AiResearchError("Gemini returned an invalid grounded answer.") from error
        return GeneratedConsumerAnswer(
            answer=parsed.answer,
            cited_evidence_numbers=parsed.cited_evidence_numbers,
            insufficient_evidence=parsed.insufficient_evidence,
            provider_response_id=_response_id(response),
        )


def _extract_grounded_sources(response: Any, fallback_text: str) -> list[GroundedWebSource]:
    candidates = getattr(response, "candidates", None) or []
    metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
    chunks = getattr(metadata, "grounding_chunks", None) or []
    supports = getattr(metadata, "grounding_supports", None) or []
    cited_segments: dict[int, list[str]] = defaultdict(list)
    for support in supports:
        segment = getattr(getattr(support, "segment", None), "text", None)
        for index in getattr(support, "grounding_chunk_indices", None) or []:
            if isinstance(index, int) and isinstance(segment, str) and segment.strip():
                cited_segments[index].append(segment.strip())

    sources: list[GroundedWebSource] = []
    seen_urls: set[str] = set()
    for index, chunk in enumerate(chunks):
        web = getattr(chunk, "web", None)
        url = getattr(web, "uri", None)
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = getattr(web, "title", None)
        domain = getattr(web, "domain", None) or urlparse(url).netloc
        cited_text = " ".join(dict.fromkeys(cited_segments.get(index, []))).strip()
        sources.append(
            GroundedWebSource(
                number=len(sources) + 1,
                title=title.strip() if isinstance(title, str) and title.strip() else domain,
                provider_name=domain,
                url=url,
                cited_text=cited_text or fallback_text[:1200],
            )
        )
    return sources


def _validate_assessments(
    assessments: list[AiResearchAssessment],
    source_count: int,
) -> list[AiResearchAssessment]:
    expected = set(AssessmentDimension)
    if {item.dimension for item in assessments} != expected:
        raise ValueError("Research must cover every assessment dimension exactly once.")
    validated: list[AiResearchAssessment] = []
    for item in assessments:
        source_numbers = list(
            dict.fromkeys(number for number in item.source_numbers if 1 <= number <= source_count)
        )
        update: dict[str, object] = {"source_numbers": source_numbers}
        if not source_numbers and item.status in {
            AssessmentStatus.SUPPORTED,
            AssessmentStatus.MIXED,
            AssessmentStatus.CONCERN,
        }:
            update["status"] = (
                AssessmentStatus.NOT_DISCLOSED
                if item.dimension
                in {AssessmentDimension.WOMEN_WORKERS, AssessmentDimension.MINORITY_INCLUSION}
                else AssessmentStatus.UNKNOWN
            )
            update["limitations"] = "No valid public source was attached to this claim."
            update["translations"] = item.translations.model_copy(
                update={
                    "pt_br": LocalizedAssessmentText(
                        finding=item.translations.pt_br.finding,
                        limitations="Nenhuma fonte pública válida foi associada a esta afirmação.",
                    ),
                    "es_latam": LocalizedAssessmentText(
                        finding=item.translations.es_latam.finding,
                        limitations="No se asoció ninguna fuente pública válida a esta afirmación.",
                    ),
                }
            )
        validated.append(item.model_copy(update=update))
    return validated


def _format_sources(sources: list[GroundedWebSource]) -> str:
    return "\n\n".join(
        f"[{source.number}] {source.title}\nURL: {source.url}\nCited text: {source.cited_text}"
        for source in sources
    )


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Gemini response did not contain text.")
    return text.strip()


def _validate_response(response: Any, schema: type[Any]) -> Any:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    return schema.model_validate_json(_response_text(response))


def _response_id(response: Any) -> str | None:
    value = getattr(response, "response_id", None)
    return value if isinstance(value, str) and value else None
