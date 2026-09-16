from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    page_number: int | None
    character_start: int
    character_end: int

    @property
    def source_location(self) -> str:
        if self.page_number is not None:
            return f"page {self.page_number}"
        return f"characters {self.character_start + 1}-{self.character_end}"


@dataclass(frozen=True)
class IndexedChunk:
    chunk: TextChunk
    embedding: list[float]


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    text: str
    chunk_index: int
    page_number: int | None
    character_start: int
    character_end: int
    source_title: str
    source_provider: str
    source_url: str
    filename: str
    similarity: float

    @property
    def source_location(self) -> str:
        if self.page_number is not None:
            return f"page {self.page_number}"
        return f"characters {self.character_start + 1}-{self.character_end}"


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    cited_chunk_numbers: list[int]
    insufficient_evidence: bool
    provider_response_id: str | None = None
