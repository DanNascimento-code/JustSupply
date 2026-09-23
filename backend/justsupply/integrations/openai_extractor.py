from openai import OpenAI, OpenAIError

from justsupply.integrations.ai import (
    EXTRACTION_INSTRUCTIONS,
    EXTRACTION_PROMPT_VERSION,
    AiExtractionError,
)
from justsupply.schemas.document_ingestion import AiExtractionOutput


class OpenAIEvidenceExtractor:
    prompt_version = EXTRACTION_PROMPT_VERSION

    def __init__(self, api_key: str, model_name: str) -> None:
        self.model_name = model_name
        self._client = OpenAI(api_key=api_key)

    def extract(self, brand_name: str, document_text: str) -> tuple[str | None, AiExtractionOutput]:
        try:
            response = self._client.responses.parse(
                model=self.model_name,
                instructions=EXTRACTION_INSTRUCTIONS,
                input=(
                    f"Brand under review: {brand_name}\n\n"
                    "Extract reviewable findings from the document below.\n\n"
                    f"<document>\n{document_text}\n</document>"
                ),
                text_format=AiExtractionOutput,
                max_output_tokens=3000,
                store=False,
            )
        except OpenAIError as error:
            raise AiExtractionError(
                "The AI extraction service is temporarily unavailable."
            ) from error

        parsed = response.output_parsed
        if parsed is None:
            raise AiExtractionError("The AI service did not return a valid structured extraction.")
        return response.id, parsed
