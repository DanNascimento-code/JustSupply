from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from justsupply.dependencies import get_rag_service
from justsupply.repositories.brand_evidence import BrandNotFoundError
from justsupply.repositories.rag import RagDocumentNotFoundError, RagPersistenceError
from justsupply.schemas.rag import (
    DocumentIndexResponse,
    RagAnswerResponse,
    RagQuestionRequest,
    RetrievalEvaluationRequest,
    RetrievalEvaluationResponse,
)
from justsupply.services.rag import RagProviderError, RagService

router = APIRouter(prefix="/rag", tags=["retrieval augmented generation"])
RagServiceDependency = Annotated[RagService, Depends(get_rag_service)]


@router.post("/brands/{brand_id}/ask", response_model=RagAnswerResponse)
def ask_brand_evidence(
    brand_id: UUID,
    payload: RagQuestionRequest,
    service: RagServiceDependency,
) -> RagAnswerResponse:
    try:
        return service.ask(brand_id, payload.question, top_k=payload.top_k)
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RagProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/documents/{document_id}/index", response_model=DocumentIndexResponse)
def index_document(
    document_id: UUID,
    service: RagServiceDependency,
) -> DocumentIndexResponse:
    try:
        chunk_count = service.index_document(document_id)
        return DocumentIndexResponse(
            document_id=document_id,
            chunk_count=chunk_count,
            embedding_model=service.retrieval_model,
        )
    except RagDocumentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RagProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except RagPersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post(
    "/brands/{brand_id}/evaluations",
    response_model=RetrievalEvaluationResponse,
)
def evaluate_brand_retrieval(
    brand_id: UUID,
    payload: RetrievalEvaluationRequest,
    service: RagServiceDependency,
) -> RetrievalEvaluationResponse:
    try:
        return service.evaluate(brand_id, payload)
    except BrandNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RagProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
