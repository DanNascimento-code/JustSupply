from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from justsupply.dependencies import get_consumer_service
from justsupply.integrations.open_food_facts import CatalogUnavailableError
from justsupply.repositories.consumer_evidence import EvidencePersistenceError
from justsupply.schemas.consumer import ConsumerSearchResponse
from justsupply.services.consumer import ConsumerService

router = APIRouter(prefix="/consumer", tags=["consumer"])
ConsumerServiceDependency = Annotated[ConsumerService, Depends(get_consumer_service)]
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
) -> ConsumerSearchResponse:
    try:
        return service.search(query)
    except CatalogUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except EvidencePersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
