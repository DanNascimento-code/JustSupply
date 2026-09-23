from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from justsupply.database.models import (
    AiExtractionRunModel,
    AiFindingModel,
    BrandModel,
    ClaimEvidenceRecordModel,
    ClaimModel,
    DocumentChunkModel,
    DocumentIngestionJobModel,
    EvidenceRecordModel,
    EvidenceSourceModel,
    SourceDocumentModel,
)
from justsupply.domain.rag import IndexedChunk
from justsupply.repositories.brand_evidence import BrandNotFoundError
from justsupply.schemas.brand_evidence import (
    EvidenceSourceType,
    ReviewDecision,
    ReviewStatus,
)
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus
from justsupply.schemas.document_ingestion import (
    AiExtractionFinding,
    DocumentIngestionJobListResponse,
    DocumentIngestionJobRead,
    DocumentListResponse,
    DocumentRead,
    ExtractedFindingRead,
)


class FindingNotFoundError(Exception):
    def __init__(self, finding_id: UUID) -> None:
        super().__init__(f"AI finding '{finding_id}' was not found.")


class DocumentPersistenceError(RuntimeError):
    pass


class DocumentIngestionJobNotFoundError(Exception):
    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"Document ingestion job '{job_id}' was not found.")


@dataclass(frozen=True)
class DocumentCreate:
    id: UUID
    brand_id: UUID
    filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    storage_path: str
    extracted_text: str
    source_title: str
    source_provider: str
    source_url: str
    source_type: EvidenceSourceType
    published_at: datetime | None
    model_name: str
    prompt_version: str
    provider_response_id: str | None
    findings: list[AiExtractionFinding]
    chunks: list[IndexedChunk]
    embedding_model: str
    embedding_dimensions: int


@dataclass(frozen=True)
class DocumentIngestionJobCreate:
    id: UUID
    brand_id: UUID
    document_id: UUID | None
    filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    storage_path: str
    source_title: str
    source_provider: str
    source_url: str
    source_type: EvidenceSourceType
    published_at: datetime | None
    status: Literal["queued", "completed"]


@dataclass(frozen=True)
class DocumentIngestionJobWorkItem:
    id: UUID
    brand_id: UUID
    filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    storage_path: str
    source_title: str
    source_provider: str
    source_url: str
    source_type: EvidenceSourceType
    published_at: datetime | None


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_brand_name(self, brand_id: UUID) -> str:
        return self._get_brand(brand_id).name

    def find_by_hash(self, brand_id: UUID, content_sha256: str) -> DocumentRead | None:
        brand = self._get_brand(brand_id)
        document = self._session.scalar(
            select(SourceDocumentModel).where(
                SourceDocumentModel.brand_id == brand_id,
                SourceDocumentModel.content_sha256 == content_sha256,
            )
        )
        if document is None:
            return None
        return self._to_read(document, brand)

    def list_documents(self, brand_id: UUID) -> DocumentListResponse:
        brand = self._get_brand(brand_id)
        documents = self._session.scalars(
            select(SourceDocumentModel)
            .where(SourceDocumentModel.brand_id == brand_id)
            .order_by(SourceDocumentModel.created_at.desc())
        ).all()
        items = [self._to_read(document, brand) for document in documents]
        return DocumentListResponse(items=items, total=len(items))

    def create_ingestion_job(
        self,
        payload: DocumentIngestionJobCreate,
    ) -> DocumentIngestionJobRead:
        self._get_brand(payload.brand_id)
        now = datetime.now(UTC)
        job = DocumentIngestionJobModel(
            id=payload.id,
            brand_id=payload.brand_id,
            document_id=payload.document_id,
            filename=payload.filename,
            media_type=payload.media_type,
            byte_size=payload.byte_size,
            content_sha256=payload.content_sha256,
            storage_path=payload.storage_path,
            source_title=payload.source_title,
            source_provider=payload.source_provider,
            source_url=payload.source_url,
            source_type=payload.source_type.value,
            published_at=payload.published_at,
            status=payload.status,
            error_message=None,
            created_at=now,
            started_at=None,
            completed_at=now if payload.status == "completed" else None,
        )
        self._session.add(job)
        self._commit_job_change("The document ingestion job could not be created.")
        return self._job_to_read(job)

    def get_ingestion_job(self, job_id: UUID) -> DocumentIngestionJobRead:
        return self._job_to_read(self._get_job(job_id))

    def list_ingestion_jobs(self, brand_id: UUID) -> DocumentIngestionJobListResponse:
        self._get_brand(brand_id)
        jobs = self._session.scalars(
            select(DocumentIngestionJobModel)
            .where(DocumentIngestionJobModel.brand_id == brand_id)
            .order_by(DocumentIngestionJobModel.created_at.desc())
            .limit(20)
        ).all()
        return DocumentIngestionJobListResponse(
            items=[self._job_to_read(job) for job in jobs],
            total=len(jobs),
        )

    def start_ingestion_job(self, job_id: UUID) -> DocumentIngestionJobWorkItem | None:
        job = self._get_job(job_id)
        if job.status == "completed":
            return None
        if job.status == "failed":
            raise DocumentPersistenceError("A failed ingestion job cannot be processed again.")
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.error_message = None
        self._commit_job_change("The document ingestion job could not be started.")
        return DocumentIngestionJobWorkItem(
            id=job.id,
            brand_id=job.brand_id,
            filename=job.filename,
            media_type=job.media_type,
            byte_size=job.byte_size,
            content_sha256=job.content_sha256,
            storage_path=job.storage_path,
            source_title=job.source_title,
            source_provider=job.source_provider,
            source_url=job.source_url,
            source_type=EvidenceSourceType(job.source_type),
            published_at=job.published_at,
        )

    def mark_ingestion_job_queued(self, job_id: UUID, message: str) -> None:
        job = self._get_job(job_id)
        job.status = "queued"
        job.error_message = message[:2000]
        job.started_at = None
        job.completed_at = None
        self._commit_job_change("The document ingestion retry could not be saved.")

    def mark_ingestion_job_completed(self, job_id: UUID, document_id: UUID) -> None:
        job = self._get_job(job_id)
        job.status = "completed"
        job.document_id = document_id
        job.error_message = None
        job.completed_at = datetime.now(UTC)
        self._commit_job_change("The completed ingestion job could not be saved.")

    def mark_ingestion_job_failed(self, job_id: UUID, message: str) -> None:
        job = self._get_job(job_id)
        job.status = "failed"
        job.error_message = message[:2000]
        job.completed_at = datetime.now(UTC)
        self._commit_job_change("The failed ingestion job could not be saved.")

    def create_document(self, payload: DocumentCreate) -> DocumentRead:
        brand = self._get_brand(payload.brand_id)
        now = datetime.now(UTC)
        document = SourceDocumentModel(
            id=payload.id,
            brand_id=payload.brand_id,
            filename=payload.filename,
            media_type=payload.media_type,
            byte_size=payload.byte_size,
            content_sha256=payload.content_sha256,
            storage_path=payload.storage_path,
            extracted_text=payload.extracted_text,
            character_count=len(payload.extracted_text),
            source_title=payload.source_title,
            source_provider=payload.source_provider,
            source_url=payload.source_url,
            source_type=payload.source_type.value,
            published_at=payload.published_at,
            created_at=now,
        )
        extraction = AiExtractionRunModel(
            id=uuid4(),
            document_id=document.id,
            model_name=payload.model_name,
            prompt_version=payload.prompt_version,
            status="completed",
            provider_response_id=payload.provider_response_id,
            error_message=None,
            created_at=now,
            completed_at=now,
        )
        self._session.add(document)
        self._session.flush()
        self._session.add(extraction)
        self._session.flush()
        self._session.add_all(
            [
                AiFindingModel(
                    id=uuid4(),
                    extraction_id=extraction.id,
                    dimension=finding.dimension.value,
                    status=finding.status.value,
                    statement=finding.statement,
                    excerpt=finding.excerpt,
                    source_location=finding.source_location,
                    rationale=finding.rationale,
                    review_status="pending",
                    reviewed_at=None,
                    published_claim_id=None,
                    created_at=now,
                )
                for finding in payload.findings
            ]
        )
        self._session.add_all(
            [
                DocumentChunkModel(
                    id=uuid4(),
                    document_id=document.id,
                    chunk_index=item.chunk.index,
                    text=item.chunk.text,
                    page_number=item.chunk.page_number,
                    character_start=item.chunk.character_start,
                    character_end=item.chunk.character_end,
                    content_sha256=_fingerprint(item.chunk.text),
                    embedding_model=payload.embedding_model,
                    embedding_dimensions=payload.embedding_dimensions,
                    embedding=item.embedding,
                    created_at=now,
                )
                for item in payload.chunks
            ]
        )
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise DocumentPersistenceError("The document extraction could not be saved.") from error
        return self._to_read(document, brand)

    def review_finding(
        self,
        finding_id: UUID,
        decision: ReviewDecision,
    ) -> ExtractedFindingRead:
        finding = self._session.get(AiFindingModel, finding_id)
        if finding is None:
            raise FindingNotFoundError(finding_id)

        extraction = self._session.get(AiExtractionRunModel, finding.extraction_id)
        if extraction is None:
            raise FindingNotFoundError(finding_id)
        document = self._session.get(SourceDocumentModel, extraction.document_id)
        if document is None:
            raise FindingNotFoundError(finding_id)
        brand = self._get_brand(document.brand_id)
        now = datetime.now(UTC)

        finding.review_status = decision.value
        finding.reviewed_at = now
        if decision == ReviewDecision.APPROVED:
            claim = self._publish_finding(finding, document, brand, now)
            finding.published_claim_id = claim.id

        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise DocumentPersistenceError("The AI finding review could not be saved.") from error
        return self._finding_to_read(finding)

    def _publish_finding(
        self,
        finding: AiFindingModel,
        document: SourceDocumentModel,
        brand: BrandModel,
        now: datetime,
    ) -> ClaimModel:
        source_url_key = _fingerprint(document.source_url)
        source = self._session.scalar(
            select(EvidenceSourceModel).where(EvidenceSourceModel.url_key == source_url_key)
        )
        if source is None:
            source = EvidenceSourceModel(
                id=uuid4(),
                url_key=source_url_key,
                created_at=now,
                updated_at=now,
            )
            self._session.add(source)
        source.provider_name = document.source_provider
        source.title = document.source_title
        source.url = document.source_url
        source.source_type = document.source_type
        source.published_at = document.published_at
        source.retrieved_at = now
        source.updated_at = now
        self._session.flush()

        claim = self._session.scalar(
            select(ClaimModel).where(
                ClaimModel.brand_id == brand.id,
                ClaimModel.dimension == finding.dimension,
            )
        )
        if claim is None:
            claim = ClaimModel(
                id=uuid4(),
                subject_scope="brand",
                product_id=None,
                brand_id=brand.id,
                dimension=finding.dimension,
                created_at=now,
                updated_at=now,
            )
            self._session.add(claim)
        claim.status = finding.status
        claim.statement = finding.statement
        claim.origin = "manual"
        claim.review_status = "approved"
        claim.reviewed_at = now
        claim.updated_at = now
        self._session.flush()

        evidence_fingerprint = _fingerprint(f"{document.content_sha256}\0{finding.id}")
        evidence = self._session.scalar(
            select(EvidenceRecordModel).where(
                EvidenceRecordModel.source_id == source.id,
                EvidenceRecordModel.fingerprint == evidence_fingerprint,
            )
        )
        if evidence is None:
            evidence = EvidenceRecordModel(
                id=uuid4(),
                source_id=source.id,
                fingerprint=evidence_fingerprint,
                summary=finding.statement,
                excerpt=finding.excerpt,
                source_location=finding.source_location,
                observed_at=document.published_at,
                collected_at=now,
                created_at=now,
            )
            self._session.add(evidence)
            self._session.flush()

        relationship = self._session.get(
            ClaimEvidenceRecordModel,
            (claim.id, evidence.id),
        )
        if relationship is None:
            self._session.add(
                ClaimEvidenceRecordModel(
                    claim_id=claim.id,
                    evidence_record_id=evidence.id,
                    relationship="supports",
                )
            )
        return claim

    def _get_brand(self, brand_id: UUID) -> BrandModel:
        brand = self._session.get(BrandModel, brand_id)
        if brand is None:
            raise BrandNotFoundError(brand_id)
        return brand

    def _get_job(self, job_id: UUID) -> DocumentIngestionJobModel:
        job = self._session.get(DocumentIngestionJobModel, job_id)
        if job is None:
            raise DocumentIngestionJobNotFoundError(job_id)
        return job

    def _commit_job_change(self, error_message: str) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise DocumentPersistenceError(error_message) from error

    def _to_read(self, document: SourceDocumentModel, brand: BrandModel) -> DocumentRead:
        extraction = self._session.scalar(
            select(AiExtractionRunModel)
            .where(AiExtractionRunModel.document_id == document.id)
            .order_by(AiExtractionRunModel.created_at.desc())
        )
        if extraction is None:
            raise DocumentPersistenceError("The document has no extraction record.")
        findings = self._session.scalars(
            select(AiFindingModel)
            .where(AiFindingModel.extraction_id == extraction.id)
            .order_by(AiFindingModel.created_at.asc())
        ).all()
        chunk_count = self._session.scalar(
            select(func.count(DocumentChunkModel.id)).where(
                DocumentChunkModel.document_id == document.id
            )
        )
        return DocumentRead(
            id=document.id,
            brand_id=brand.id,
            brand_name=brand.name,
            filename=document.filename,
            media_type=document.media_type,
            byte_size=document.byte_size,
            content_sha256=document.content_sha256,
            character_count=document.character_count,
            source_title=document.source_title,
            source_provider=document.source_provider,
            source_url=document.source_url,
            source_type=EvidenceSourceType(document.source_type),
            published_at=document.published_at,
            model_name=extraction.model_name,
            prompt_version=extraction.prompt_version,
            extraction_status=cast(Literal["completed", "failed"], extraction.status),
            chunk_count=chunk_count or 0,
            created_at=document.created_at,
            findings=[self._finding_to_read(finding) for finding in findings],
        )

    @staticmethod
    def _job_to_read(job: DocumentIngestionJobModel) -> DocumentIngestionJobRead:
        return DocumentIngestionJobRead(
            id=job.id,
            brand_id=job.brand_id,
            document_id=job.document_id,
            filename=job.filename,
            source_title=job.source_title,
            status=cast(
                Literal["queued", "processing", "completed", "failed"],
                job.status,
            ),
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    @staticmethod
    def _finding_to_read(finding: AiFindingModel) -> ExtractedFindingRead:
        return ExtractedFindingRead(
            id=finding.id,
            dimension=AssessmentDimension(finding.dimension),
            status=AssessmentStatus(finding.status),
            statement=finding.statement,
            excerpt=finding.excerpt,
            source_location=finding.source_location,
            rationale=finding.rationale,
            review_status=ReviewStatus(finding.review_status),
            reviewed_at=finding.reviewed_at,
            published_claim_id=finding.published_claim_id,
        )


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
