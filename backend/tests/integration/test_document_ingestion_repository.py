import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from justsupply.database.models import (
    BrandModel,
    ClaimModel,
    DocumentChunkModel,
    EvidenceSourceModel,
)
from justsupply.database.session import SessionFactory
from justsupply.domain.rag import IndexedChunk, TextChunk
from justsupply.repositories.document_ingestion import (
    DocumentCreate,
    DocumentIngestionJobCreate,
    SqlAlchemyDocumentRepository,
)
from justsupply.schemas.brand_evidence import EvidenceSourceType, ReviewDecision
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus
from justsupply.schemas.document_ingestion import AiExtractionFinding

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="Set RUN_DATABASE_TESTS=1 to run PostgreSQL integration tests.",
    ),
]


def test_approved_ai_finding_becomes_consumer_claim() -> None:
    unique_suffix = uuid4().hex[:12]
    brand_id = uuid4()
    document_id = uuid4()
    now = datetime.now(UTC)
    source_url = f"https://example.org/ai-reports/{unique_suffix}"

    with SessionFactory() as session:
        session.add(
            BrandModel(
                id=brand_id,
                name=f"AI review brand {unique_suffix}",
                name_key=f"ai review brand {unique_suffix}",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        repository = SqlAlchemyDocumentRepository(session)
        queued_job = repository.create_ingestion_job(
            DocumentIngestionJobCreate(
                id=document_id,
                brand_id=brand_id,
                document_id=None,
                filename="impact-report.txt",
                media_type="text/plain",
                byte_size=180,
                content_sha256=unique_suffix.ljust(64, "0"),
                storage_path=f"data/uploads/{document_id}.txt",
                source_title="2025 Impact Report",
                source_provider="Example Organization",
                source_url=source_url,
                source_type=EvidenceSourceType.CORPORATE_REPORT,
                published_at=datetime(2025, 12, 1, tzinfo=UTC),
                status="queued",
            )
        )

        assert queued_job.status == "queued"
        work_item = repository.start_ingestion_job(document_id)
        assert work_item is not None
        assert repository.get_ingestion_job(document_id).status == "processing"

        document = repository.create_document(
            DocumentCreate(
                id=document_id,
                brand_id=brand_id,
                filename="impact-report.txt",
                media_type="text/plain",
                byte_size=180,
                content_sha256=unique_suffix.ljust(64, "0"),
                storage_path=f"data/uploads/{document_id}.txt",
                extracted_text=(
                    "Women represented 48 percent of program participants, according to "
                    "the program results published in this report."
                ),
                source_title="2025 Impact Report",
                source_provider="Example Organization",
                source_url=source_url,
                source_type=EvidenceSourceType.CORPORATE_REPORT,
                published_at=datetime(2025, 12, 1, tzinfo=UTC),
                model_name="test-model",
                prompt_version="social-evidence-v1",
                provider_response_id="resp_test",
                findings=[
                    AiExtractionFinding(
                        dimension=AssessmentDimension.WOMEN_WORKERS,
                        status=AssessmentStatus.SUPPORTED,
                        statement=(
                            "The report documents participation by women in a company program."
                        ),
                        excerpt="Women represented 48 percent of program participants",
                        source_location="page 12",
                        rationale="The passage directly quantifies participation by women.",
                    )
                ],
                chunks=[
                    IndexedChunk(
                        chunk=TextChunk(
                            index=0,
                            text=(
                                "Women represented 48 percent of program participants, according "
                                "to the program results published in this report."
                            ),
                            page_number=12,
                            character_start=0,
                            character_end=116,
                        ),
                        embedding=[0.0] * 1536,
                    )
                ],
                embedding_model="test-embedding-model",
                embedding_dimensions=1536,
            )
        )
        repository.mark_ingestion_job_completed(document_id, document.id)

        assert document.findings[0].review_status == "pending"
        assert document.chunk_count == 1
        completed_job = repository.get_ingestion_job(document_id)
        assert completed_job.status == "completed"
        assert completed_job.document_id == document.id
        assert (
            session.scalar(
                select(DocumentChunkModel).where(DocumentChunkModel.document_id == document_id)
            )
            is not None
        )
        reviewed = repository.review_finding(
            document.findings[0].id,
            ReviewDecision.APPROVED,
        )

        assert reviewed.review_status == "approved"
        assert reviewed.published_claim_id is not None
        claim = session.scalar(
            select(ClaimModel).where(
                ClaimModel.brand_id == brand_id,
                ClaimModel.dimension == "women_workers",
            )
        )
        assert claim is not None
        assert claim.review_status == "approved"
        assert claim.origin == "manual"

        session.execute(delete(EvidenceSourceModel).where(EvidenceSourceModel.url == source_url))
        session.execute(delete(BrandModel).where(BrandModel.id == brand_id))
        session.commit()
