from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import HttpUrl, ValidationError

from justsupply.dependencies import get_document_ingestion_service
from justsupply.integrations.document_parser import DocumentValidationError
from justsupply.repositories.brand_evidence import BrandNotFoundError
from justsupply.repositories.document_ingestion import (
    DocumentIngestionJobNotFoundError,
    DocumentPersistenceError,
    FindingNotFoundError,
)
from justsupply.schemas.brand_evidence import EvidenceSourceType
from justsupply.schemas.document_ingestion import (
    DocumentIngestionJobListResponse,
    DocumentIngestionJobRead,
    DocumentListResponse,
    DocumentMetadata,
    ExtractedFindingRead,
    FindingReviewUpdate,
)
from justsupply.services.document_ingestion import (
    DocumentIngestionService,
    DocumentJobDispatchError,
)

router = APIRouter(prefix="/evidence", tags=["evidence documents"])
DocumentServiceDependency = Annotated[
    DocumentIngestionService,
    Depends(get_document_ingestion_service),
]


@router.get("/brands/{brand_id}/documents", response_model=DocumentListResponse)
def list_documents(
    brand_id: UUID,
    service: DocumentServiceDependency,
) -> DocumentListResponse:
    try:
        return service.list_documents(brand_id)
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post(
    "/brands/{brand_id}/documents",
    response_model=DocumentIngestionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_document(
    brand_id: UUID,
    service: DocumentServiceDependency,
    file: Annotated[UploadFile, File()],
    source_title: Annotated[str, Form(min_length=3, max_length=300)],
    source_provider: Annotated[str, Form(min_length=2, max_length=200)],
    source_url: Annotated[HttpUrl, Form()],
    source_type: Annotated[EvidenceSourceType, Form()],
    published_at: Annotated[datetime | None, Form()] = None,
) -> DocumentIngestionJobRead:
    content = await file.read(service.max_bytes + 1)
    try:
        metadata = DocumentMetadata(
            source_title=source_title,
            source_provider=source_provider,
            source_url=source_url,
            source_type=source_type,
            published_at=published_at,
        )
        return service.enqueue(
            brand_id,
            metadata,
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
        )
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (DocumentValidationError, ValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except DocumentJobDispatchError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except DocumentPersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    finally:
        await file.close()


@router.get(
    "/brands/{brand_id}/ingestion-jobs",
    response_model=DocumentIngestionJobListResponse,
)
def list_ingestion_jobs(
    brand_id: UUID,
    service: DocumentServiceDependency,
) -> DocumentIngestionJobListResponse:
    try:
        return service.list_jobs(brand_id)
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get(
    "/ingestion-jobs/{job_id}",
    response_model=DocumentIngestionJobRead,
)
def get_ingestion_job(
    job_id: UUID,
    service: DocumentServiceDependency,
) -> DocumentIngestionJobRead:
    try:
        return service.get_job(job_id)
    except DocumentIngestionJobNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.patch("/findings/{finding_id}/review", response_model=ExtractedFindingRead)
def review_finding(
    finding_id: UUID,
    payload: FindingReviewUpdate,
    service: DocumentServiceDependency,
) -> ExtractedFindingRead:
    try:
        return service.review_finding(finding_id, payload.decision)
    except FindingNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except DocumentPersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
