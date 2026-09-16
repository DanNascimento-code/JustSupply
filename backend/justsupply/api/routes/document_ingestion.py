from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import HttpUrl, ValidationError

from justsupply.dependencies import get_document_ingestion_service
from justsupply.integrations.document_parser import DocumentValidationError
from justsupply.integrations.openai_extractor import AiExtractionError
from justsupply.repositories.brand_evidence import BrandNotFoundError
from justsupply.repositories.document_ingestion import (
    DocumentPersistenceError,
    FindingNotFoundError,
)
from justsupply.schemas.brand_evidence import EvidenceSourceType
from justsupply.schemas.document_ingestion import (
    DocumentListResponse,
    DocumentMetadata,
    DocumentRead,
    ExtractedFindingRead,
    FindingReviewUpdate,
)
from justsupply.services.document_ingestion import DocumentIngestionService

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
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
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
) -> DocumentRead:
    content = await file.read(service.max_bytes + 1)
    try:
        metadata = DocumentMetadata(
            source_title=source_title,
            source_provider=source_provider,
            source_url=source_url,
            source_type=source_type,
            published_at=published_at,
        )
        return service.ingest(
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
    except AiExtractionError as error:
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
