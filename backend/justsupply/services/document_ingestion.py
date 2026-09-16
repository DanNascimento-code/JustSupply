import re
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from justsupply.integrations.document_parser import ParsedDocument, parse_document
from justsupply.integrations.openai_extractor import EvidenceExtractor
from justsupply.repositories.document_ingestion import (
    DocumentCreate,
    SqlAlchemyDocumentRepository,
)
from justsupply.schemas.brand_evidence import ReviewDecision
from justsupply.schemas.document_ingestion import (
    AiExtractionFinding,
    DocumentListResponse,
    DocumentMetadata,
    DocumentRead,
    ExtractedFindingRead,
)
from justsupply.services.rag import RagIndexingService


class DocumentIngestionService:
    def __init__(
        self,
        repository: SqlAlchemyDocumentRepository,
        extractor: EvidenceExtractor,
        indexer: RagIndexingService,
        *,
        upload_directory: Path,
        max_bytes: int,
        max_characters: int,
    ) -> None:
        self._repository = repository
        self._extractor = extractor
        self._indexer = indexer
        self._upload_directory = upload_directory
        self._max_bytes = max_bytes
        self._max_characters = max_characters

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def list_documents(self, brand_id: UUID) -> DocumentListResponse:
        return self._repository.list_documents(brand_id)

    def ingest(
        self,
        brand_id: UUID,
        metadata: DocumentMetadata,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> DocumentRead:
        brand_name = self._repository.get_brand_name(brand_id)
        content_sha256 = sha256(content).hexdigest()
        existing = self._repository.find_by_hash(brand_id, content_sha256)
        if existing is not None:
            return existing

        parsed = parse_document(
            filename,
            content_type,
            content,
            max_bytes=self._max_bytes,
            max_characters=self._max_characters,
        )
        provider_response_id, extraction = self._extractor.extract(brand_name, parsed.text)
        chunks = self._indexer.prepare(parsed.text)
        verified_findings = [
            finding for finding in extraction.findings if _excerpt_exists(finding, parsed)
        ]

        document_id = uuid4()
        storage_path = self._store_file(document_id, parsed, content)
        try:
            return self._repository.create_document(
                DocumentCreate(
                    id=document_id,
                    brand_id=brand_id,
                    filename=parsed.filename,
                    media_type=parsed.media_type,
                    byte_size=len(content),
                    content_sha256=content_sha256,
                    storage_path=str(storage_path),
                    extracted_text=parsed.text,
                    source_title=metadata.source_title,
                    source_provider=metadata.source_provider,
                    source_url=str(metadata.source_url),
                    source_type=metadata.source_type,
                    published_at=metadata.published_at,
                    model_name=self._extractor.model_name,
                    prompt_version=self._extractor.prompt_version,
                    provider_response_id=provider_response_id,
                    findings=verified_findings,
                    chunks=chunks,
                    embedding_model=self._indexer.embedding_model,
                    embedding_dimensions=self._indexer.embedding_dimensions,
                )
            )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

    def review_finding(
        self,
        finding_id: UUID,
        decision: ReviewDecision,
    ) -> ExtractedFindingRead:
        return self._repository.review_finding(finding_id, decision)

    def _store_file(self, document_id: UUID, parsed: ParsedDocument, content: bytes) -> Path:
        self._upload_directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(parsed.filename).suffix.lower()
        path = (self._upload_directory / f"{document_id}{suffix}").resolve()
        upload_root = self._upload_directory.resolve()
        if upload_root not in path.parents:
            raise ValueError("The document storage path is invalid.")
        path.write_bytes(content)
        return path


def _excerpt_exists(finding: AiExtractionFinding, document: ParsedDocument) -> bool:
    normalized_document = _normalize_whitespace(document.text)
    normalized_excerpt = _normalize_whitespace(finding.excerpt)
    return normalized_excerpt in normalized_document


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
