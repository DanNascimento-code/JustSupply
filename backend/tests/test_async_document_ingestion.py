from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from justsupply.repositories.document_ingestion import (
    DocumentCreate,
    DocumentIngestionJobCreate,
    DocumentIngestionJobWorkItem,
)
from justsupply.schemas.brand_evidence import EvidenceSourceType
from justsupply.schemas.document_ingestion import (
    AiExtractionOutput,
    DocumentIngestionJobRead,
    DocumentMetadata,
    DocumentRead,
)
from justsupply.services.document_ingestion import (
    DocumentIngestionProcessor,
    DocumentIngestionService,
    DocumentJobDispatchError,
)

BRAND_ID = UUID("c65e471a-8e8e-4d89-a493-99d04b56154f")
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
CONTENT = b"Women represented 48 percent of program participants in leadership training."


class RecordingDispatcher:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.job_ids: list[UUID] = []
        self.should_fail = should_fail

    def enqueue(self, job_id: UUID) -> None:
        self.job_ids.append(job_id)
        if self.should_fail:
            raise RuntimeError("Redis is unavailable")


class QueueRepository:
    def __init__(self) -> None:
        self.created: DocumentIngestionJobCreate | None = None
        self.failed: tuple[UUID, str] | None = None

    def get_brand_name(self, brand_id: UUID) -> str:
        assert brand_id == BRAND_ID
        return "Example Foods"

    def create_ingestion_job(
        self,
        payload: DocumentIngestionJobCreate,
    ) -> DocumentIngestionJobRead:
        self.created = payload
        return DocumentIngestionJobRead(
            id=payload.id,
            brand_id=payload.brand_id,
            document_id=None,
            filename=payload.filename,
            source_title=payload.source_title,
            status="queued",
            error_message=None,
            created_at=NOW,
            started_at=None,
            completed_at=None,
        )

    def mark_ingestion_job_failed(self, job_id: UUID, message: str) -> None:
        self.failed = (job_id, message)


def metadata() -> DocumentMetadata:
    return DocumentMetadata(
        source_title="2025 Impact Report",
        source_provider="Example Foods",
        source_url="https://example.org/report",
        source_type=EvidenceSourceType.CORPORATE_REPORT,
        published_at=None,
    )


def test_enqueue_persists_upload_and_sends_only_job_id(tmp_path: Path) -> None:
    repository = QueueRepository()
    dispatcher = RecordingDispatcher()
    service = DocumentIngestionService(  # type: ignore[arg-type]
        repository,
        dispatcher,
        upload_directory=tmp_path,
        max_bytes=1024,
    )

    job = service.enqueue(
        BRAND_ID,
        metadata(),
        filename="impact-report.txt",
        content_type="text/plain",
        content=CONTENT,
    )

    assert dispatcher.job_ids == [job.id]
    assert repository.created is not None
    assert Path(repository.created.storage_path).read_bytes() == CONTENT
    assert repository.created.status == "queued"


def test_enqueue_marks_job_failed_and_removes_upload_when_dispatch_fails(
    tmp_path: Path,
) -> None:
    repository = QueueRepository()
    dispatcher = RecordingDispatcher(should_fail=True)
    service = DocumentIngestionService(  # type: ignore[arg-type]
        repository,
        dispatcher,
        upload_directory=tmp_path,
        max_bytes=1024,
    )

    with pytest.raises(DocumentJobDispatchError, match="queue is unavailable"):
        service.enqueue(
            BRAND_ID,
            metadata(),
            filename="impact-report.txt",
            content_type="text/plain",
            content=CONTENT,
        )

    assert repository.failed is not None
    assert list(tmp_path.iterdir()) == []


class ProcessorRepository:
    def __init__(self, work_item: DocumentIngestionJobWorkItem) -> None:
        self.work_item = work_item
        self.created: DocumentCreate | None = None
        self.completed: tuple[UUID, UUID] | None = None

    def start_ingestion_job(self, job_id: UUID) -> DocumentIngestionJobWorkItem:
        assert job_id == self.work_item.id
        return self.work_item

    def find_by_hash(self, brand_id: UUID, content_sha256: str) -> None:
        assert brand_id == BRAND_ID
        assert content_sha256 == self.work_item.content_sha256
        return None

    def get_brand_name(self, brand_id: UUID) -> str:
        assert brand_id == BRAND_ID
        return "Example Foods"

    def create_document(self, payload: DocumentCreate) -> DocumentRead:
        self.created = payload
        return DocumentRead(
            id=payload.id,
            brand_id=payload.brand_id,
            brand_name="Example Foods",
            filename=payload.filename,
            media_type=payload.media_type,
            byte_size=payload.byte_size,
            content_sha256=payload.content_sha256,
            character_count=len(payload.extracted_text),
            source_title=payload.source_title,
            source_provider=payload.source_provider,
            source_url=payload.source_url,
            source_type=payload.source_type,
            published_at=payload.published_at,
            model_name=payload.model_name,
            prompt_version=payload.prompt_version,
            extraction_status="completed",
            chunk_count=len(payload.chunks),
            created_at=NOW,
            findings=[],
        )

    def mark_ingestion_job_completed(self, job_id: UUID, document_id: UUID) -> None:
        self.completed = (job_id, document_id)


class EmptyExtractor:
    model_name = "test-model"
    prompt_version = "test-prompt-v1"

    def extract(self, brand_name: str, document_text: str) -> tuple[str, AiExtractionOutput]:
        assert brand_name == "Example Foods"
        assert "leadership training" in document_text
        return "test-response", AiExtractionOutput(findings=[])


class EmptyIndexer:
    embedding_model = "test-embedding"
    embedding_dimensions = 1536

    def prepare(self, text: str) -> list[object]:
        assert "leadership training" in text
        return []


def test_processor_reads_stored_upload_and_completes_job(tmp_path: Path) -> None:
    from hashlib import sha256

    job_id = UUID("f9482497-e195-4866-ad3f-3679d83ef7ef")
    upload_path = tmp_path / f"{job_id}.txt"
    upload_path.write_bytes(CONTENT)
    work_item = DocumentIngestionJobWorkItem(
        id=job_id,
        brand_id=BRAND_ID,
        filename="impact-report.txt",
        media_type="text/plain",
        byte_size=len(CONTENT),
        content_sha256=sha256(CONTENT).hexdigest(),
        storage_path=str(upload_path),
        source_title="2025 Impact Report",
        source_provider="Example Foods",
        source_url="https://example.org/report",
        source_type=EvidenceSourceType.CORPORATE_REPORT,
        published_at=None,
    )
    repository = ProcessorRepository(work_item)
    processor = DocumentIngestionProcessor(  # type: ignore[arg-type]
        repository,
        EmptyExtractor(),
        EmptyIndexer(),
        upload_directory=tmp_path,
        max_bytes=1024,
        max_characters=2000,
    )

    document = processor.process(job_id)

    assert document is not None
    assert repository.created is not None
    assert repository.created.provider_response_id == "test-response"
    assert repository.completed == (job_id, job_id)
