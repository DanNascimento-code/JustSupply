from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from justsupply.dependencies import get_consumer_research_service, get_consumer_service
from justsupply.integrations.ai import AiResearchError
from justsupply.integrations.open_food_facts import CatalogUnavailableError
from justsupply.repositories.consumer_evidence import (
    EvidencePersistenceError,
    ProductNotFoundError,
)
from justsupply.schemas.consumer import (
    ConsumerAnswerResponse,
    ConsumerQuestionRequest,
    ConsumerSearchResponse,
    ProductResearchResponse,
    UserLocale,
)
from justsupply.services.consumer import (
    ConsumerProductNotFoundError,
    ConsumerResearchService,
    ConsumerService,
)

router = APIRouter(prefix="/consumer", tags=["consumer"])
ConsumerServiceDependency = Annotated[ConsumerService, Depends(get_consumer_service)]
ResearchServiceDependency = Annotated[
    ConsumerResearchService,
    Depends(get_consumer_research_service),
]
SearchQuery = Annotated[
    str,
    Query(
        min_length=2,
        max_length=120,
        description="A product name, brand name, or an 8-14 digit barcode.",
    ),
]


@router.get("/products", response_model=ConsumerSearchResponse)
def search_products(
    service: ConsumerServiceDependency,
    query: SearchQuery,
    language: UserLocale = UserLocale.ENGLISH,
) -> ConsumerSearchResponse:
    try:
        return service.search(query, language)
    except CatalogUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except EvidencePersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/products/{barcode}/research", response_model=ProductResearchResponse)
def research_product(
    barcode: str,
    service: ResearchServiceDependency,
    refresh: bool = False,
    language: UserLocale = UserLocale.ENGLISH,
) -> ProductResearchResponse:
    try:
        return service.research(barcode, refresh=refresh, language=language)
    except ConsumerProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CatalogUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except (AiResearchError, EvidencePersistenceError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/products/{barcode}/ask", response_model=ConsumerAnswerResponse)
def ask_product_question(
    barcode: str,
    payload: ConsumerQuestionRequest,
    service: ResearchServiceDependency,
) -> ConsumerAnswerResponse:
    try:
        return service.ask(
            barcode,
            payload.question,
            top_k=payload.top_k,
            language=payload.language,
        )
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AiResearchError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
