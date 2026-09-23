from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from justsupply.dependencies import get_document_ingestion_service
from justsupply.integrations.document_parser import DocumentValidationError, parse_document
from justsupply.main import app
from justsupply.schemas.brand_evidence import EvidenceSourceType, ReviewDecision, ReviewStatus
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus
from justsupply.schemas.document_ingestion import (
    DocumentIngestionJobListResponse,
    DocumentIngestionJobRead,
    DocumentListResponse,
    DocumentMetadata,
    DocumentRead,
    ExtractedFindingRead,
)

BRAND_ID = UUID("c65e471a-8e8e-4d89-a493-99d04b56154f")
DOCUMENT_ID = UUID("ad637cba-4450-4b8f-8798-902a34783bd2")
JOB_ID = UUID("f9482497-e195-4866-ad3f-3679d83ef7ef")
FINDING_ID = UUID("355bdf9a-11dc-43bf-b106-a010443a3775")


def finding_response(review_status: ReviewStatus = ReviewStatus.PENDING) -> ExtractedFindingRead:
    return ExtractedFindingRead(
        id=FINDING_ID,
        dimension=AssessmentDimension.WOMEN_WORKERS,
        status=AssessmentStatus.SUPPORTED,
        statement="The report documents a leadership program for women workers.",
        excerpt="Women represented 48 percent of program participants.",
        source_location="page 12",
        rationale="The passage directly reports participation by women.",
        review_status=review_status,
        reviewed_at=None,
        published_claim_id=None,
    )


def document_response() -> DocumentRead:
    return DocumentRead(
        id=DOCUMENT_ID,
        brand_id=BRAND_ID,
        brand_name="Example Foods",
        filename="impact-report.txt",
        media_type="text/plain",
        byte_size=120,
        content_sha256="a" * 64,
        character_count=120,
        source_title="2025 Impact Report",
        source_provider="Example Foods",
        source_url="https://example.org/report",
        source_type=EvidenceSourceType.CORPORATE_REPORT,
        published_at=datetime(2025, 12, 1, tzinfo=UTC),
        model_name="test-model",
        prompt_version="social-evidence-v1",
        extraction_status="completed",
        created_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        findings=[finding_response()],
    )


def job_response() -> DocumentIngestionJobRead:
    return DocumentIngestionJobRead(
        id=JOB_ID,
        brand_id=BRAND_ID,
        document_id=None,
        filename="impact-report.txt",
        source_title="2025 Impact Report",
        status="queued",
        error_message=None,
        created_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        started_at=None,
        completed_at=None,
    )


class StubDocumentService:
    max_bytes = 1024

    def list_documents(self, brand_id: UUID) -> DocumentListResponse:
        assert brand_id == BRAND_ID
        return DocumentListResponse(items=[document_response()], total=1)

    def list_jobs(self, brand_id: UUID) -> DocumentIngestionJobListResponse:
        assert brand_id == BRAND_ID
        return DocumentIngestionJobListResponse(items=[job_response()], total=1)

    def get_job(self, job_id: UUID) -> DocumentIngestionJobRead:
        assert job_id == JOB_ID
        return job_response()

    def enqueue(
        self,
        brand_id: UUID,
        metadata: DocumentMetadata,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> DocumentIngestionJobRead:
        assert brand_id == BRAND_ID
        assert metadata.source_title == "2025 Impact Report"
        assert filename == "impact-report.txt"
        assert content_type == "text/plain"
        assert b"women workers" in content
        return job_response()

    def review_finding(
        self,
        finding_id: UUID,
        decision: ReviewDecision,
    ) -> ExtractedFindingRead:
        assert finding_id == FINDING_ID
        assert decision == ReviewDecision.APPROVED
        return finding_response(ReviewStatus.APPROVED)


def test_document_routes_upload_list_and_review(client: TestClient) -> None:
    app.dependency_overrides[get_document_ingestion_service] = lambda: StubDocumentService()
    document_text = (
        "This report describes women workers participating in a leadership program "
        "and documents the program outcomes."
    )

    upload_response = client.post(
        f"/api/v1/evidence/brands/{BRAND_ID}/documents",
        data={
            "source_title": "2025 Impact Report",
            "source_provider": "Example Foods",
            "source_url": "https://example.org/report",
            "source_type": "corporate_report",
            "published_at": "2025-12-01T00:00:00Z",
        },
        files={"file": ("impact-report.txt", document_text, "text/plain")},
    )
    list_response = client.get(f"/api/v1/evidence/brands/{BRAND_ID}/documents")
    jobs_response = client.get(f"/api/v1/evidence/brands/{BRAND_ID}/ingestion-jobs")
    job_response_result = client.get(f"/api/v1/evidence/ingestion-jobs/{JOB_ID}")
    review_response = client.patch(
        f"/api/v1/evidence/findings/{FINDING_ID}/review",
        json={"decision": "approved"},
    )

    assert upload_response.status_code == 202
    assert upload_response.json()["status"] == "queued"
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert jobs_response.status_code == 200
    assert jobs_response.json()["items"][0]["id"] == str(JOB_ID)
    assert job_response_result.status_code == 200
    assert job_response_result.json()["status"] == "queued"
    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "approved"


def test_text_document_parser_accepts_utf8() -> None:
    content = (
        b"The report states that women workers participated in leadership training "
        b"and provides a breakdown of program outcomes."
    )

    parsed = parse_document(
        "report.txt",
        "text/plain",
        content,
        max_bytes=1024,
        max_characters=1000,
    )

    assert parsed.filename == "report.txt"
    assert parsed.media_type == "text/plain"
    assert "leadership training" in parsed.text


def test_document_parser_rejects_unsupported_files() -> None:
    with pytest.raises(DocumentValidationError, match="PDF, TXT, or Markdown"):
        parse_document(
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"This content is long enough to pass the text length requirement.",
            max_bytes=1024,
            max_characters=1000,
        )
