import re
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from justsupply.integrations.ai import AiExtractionError, EvidenceExtractor
from justsupply.integrations.document_parser import (
    DocumentValidationError,
    ParsedDocument,
    parse_document,
    validate_document_upload,
)
from justsupply.repositories.document_ingestion import (
    DocumentCreate,
    DocumentIngestionJobCreate,
    SqlAlchemyDocumentRepository,
)
from justsupply.schemas.brand_evidence import ReviewDecision
from justsupply.schemas.document_ingestion import (
    AiExtractionFinding,
    DocumentIngestionJobListResponse,
    DocumentIngestionJobRead,
    DocumentListResponse,
    DocumentMetadata,
    DocumentRead,
    ExtractedFindingRead,
)
from justsupply.services.rag import RagIndexingService, RagProviderError


class DocumentJobDispatchError(RuntimeError):
    pass


class DocumentJobDispatcher(Protocol):
    def enqueue(self, job_id: UUID) -> None:
        pass


class DocumentIngestionService:
    def __init__(
        self,
        repository: SqlAlchemyDocumentRepository,
        dispatcher: DocumentJobDispatcher,
        *,
        upload_directory: Path,
        max_bytes: int,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher
        self._upload_directory = upload_directory
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def list_documents(self, brand_id: UUID) -> DocumentListResponse:
        return self._repository.list_documents(brand_id)

    def list_jobs(self, brand_id: UUID) -> DocumentIngestionJobListResponse:
        return self._repository.list_ingestion_jobs(brand_id)

    def get_job(self, job_id: UUID) -> DocumentIngestionJobRead:
        return self._repository.get_ingestion_job(job_id)

    def enqueue(
        self,
        brand_id: UUID,
        metadata: DocumentMetadata,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> DocumentIngestionJobRead:
        self._repository.get_brand_name(brand_id)
        validated = validate_document_upload(
            filename,
            content_type,
            content,
            max_bytes=self._max_bytes,
        )
        job_id = uuid4()
        storage_path = self._store_upload(job_id, validated.filename, content)
        try:
            job = self._repository.create_ingestion_job(
                DocumentIngestionJobCreate(
                    id=job_id,
                    brand_id=brand_id,
                    document_id=None,
                    filename=validated.filename,
                    media_type=validated.media_type,
                    byte_size=len(content),
                    content_sha256=sha256(content).hexdigest(),
                    storage_path=str(storage_path),
                    source_title=metadata.source_title,
                    source_provider=metadata.source_provider,
                    source_url=str(metadata.source_url),
                    source_type=metadata.source_type,
                    published_at=metadata.published_at,
                    status="queued",
                )
            )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

        try:
            self._dispatcher.enqueue(job.id)
        except Exception as error:
            message = "The background worker queue is unavailable."
            self._repository.mark_ingestion_job_failed(job.id, message)
            storage_path.unlink(missing_ok=True)
            raise DocumentJobDispatchError(message) from error
        return job

    def review_finding(
        self,
        finding_id: UUID,
        decision: ReviewDecision,
    ) -> ExtractedFindingRead:
        return self._repository.review_finding(finding_id, decision)

    def _store_upload(self, job_id: UUID, filename: str, content: bytes) -> Path:
        self._upload_directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower()
        path = (self._upload_directory / f"{job_id}{suffix}").resolve()
        upload_root = self._upload_directory.resolve()
        if upload_root not in path.parents:
            raise ValueError("The document storage path is invalid.")
        path.write_bytes(content)
        return path


class DocumentIngestionProcessor:
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
        self._upload_directory = upload_directory.resolve()
        self._max_bytes = max_bytes
        self._max_characters = max_characters

    def process(self, job_id: UUID) -> DocumentRead | None:
        job = self._repository.start_ingestion_job(job_id)
        if job is None:
            return None

        existing = self._repository.find_by_hash(job.brand_id, job.content_sha256)
        if existing is not None:
            self._safe_job_path(job.storage_path).unlink(missing_ok=True)
            self._repository.mark_ingestion_job_completed(job.id, existing.id)
            return existing

        storage_path = self._safe_job_path(job.storage_path)
        content = storage_path.read_bytes()
        if sha256(content).hexdigest() != job.content_sha256:
            raise ValueError("The stored upload failed its integrity check.")

        parsed = parse_document(
            job.filename,
            job.media_type,
            content,
            max_bytes=self._max_bytes,
            max_characters=self._max_characters,
        )
        brand_name = self._repository.get_brand_name(job.brand_id)
        provider_response_id, extraction = self._extractor.extract(brand_name, parsed.text)
        chunks = self._indexer.prepare(parsed.text)
        verified_findings = [
            finding for finding in extraction.findings if _excerpt_exists(finding, parsed)
        ]
        document = self._repository.create_document(
            DocumentCreate(
                id=job.id,
                brand_id=job.brand_id,
                filename=parsed.filename,
                media_type=parsed.media_type,
                byte_size=job.byte_size,
                content_sha256=job.content_sha256,
                storage_path=str(storage_path),
                extracted_text=parsed.text,
                source_title=job.source_title,
                source_provider=job.source_provider,
                source_url=job.source_url,
                source_type=job.source_type,
                published_at=job.published_at,
                model_name=self._extractor.model_name,
                prompt_version=self._extractor.prompt_version,
                provider_response_id=provider_response_id,
                findings=verified_findings,
                chunks=chunks,
                embedding_model=self._indexer.embedding_model,
                embedding_dimensions=self._indexer.embedding_dimensions,
            )
        )
        self._repository.mark_ingestion_job_completed(job.id, document.id)
        return document

    def defer(self, job_id: UUID, error: Exception) -> None:
        self._repository.mark_ingestion_job_queued(job_id, _safe_error_message(error))

    def fail(self, job_id: UUID, error: Exception) -> None:
        self._repository.mark_ingestion_job_failed(job_id, _safe_error_message(error))

    def _safe_job_path(self, value: str) -> Path:
        path = Path(value).resolve()
        if self._upload_directory not in path.parents:
            raise ValueError("The document storage path is invalid.")
        return path


def _excerpt_exists(finding: AiExtractionFinding, document: ParsedDocument) -> bool:
    normalized_document = _normalize_whitespace(document.text)
    normalized_excerpt = _normalize_whitespace(finding.excerpt)
    return normalized_excerpt in normalized_document


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _safe_error_message(error: Exception) -> str:
    if not isinstance(
        error,
        (AiExtractionError, DocumentValidationError, RagProviderError, ValueError),
    ):
        return "Document processing failed. Check the worker logs for details."
    message = str(error).strip()
    return message[:2000] if message else error.__class__.__name__
