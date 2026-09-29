from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from justsupply.core.config import get_settings
from justsupply.database.session import get_database_session
from justsupply.integrations.ai import (
    AiResearcher,
    ConsumerAnswerGenerator,
    EmbeddingProvider,
    PublicWebSearchProvider,
    UnavailableAnswerGenerator,
    UnavailableEmbeddingProvider,
    UnavailableResearcher,
)
from justsupply.integrations.composite_catalog import FallbackProductCatalog
from justsupply.integrations.composite_search import CompositeWebSearch
from justsupply.integrations.gemini import (
    GeminiConsumerAnswerGenerator,
    GeminiEmbeddingProvider,
    GeminiEvidenceResearcher,
)
from justsupply.integrations.google_grounding import GoogleGroundedSearch
from justsupply.integrations.langchain_rag import LangChainConsumerRag
from justsupply.integrations.open_food_facts import OpenFoodFactsCatalog
from justsupply.integrations.tavily import TavilyWebSearch
from justsupply.integrations.usda_food_data import UsdaFoodDataCatalog
from justsupply.integrations.wikidata import WikidataOrganizationResolver
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.services.consumer import ConsumerResearchService, ConsumerService


def get_consumer_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> Iterator[ConsumerService]:
    catalog = _catalog()
    try:
        yield ConsumerService(
            catalog,
            SqlAlchemyConsumerEvidenceRepository(session),
            catalog_cache_ttl_hours=get_settings().catalog_cache_ttl_hours,
        )
    finally:
        catalog.close()


def get_consumer_research_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> Iterator[ConsumerResearchService]:
    settings = get_settings()
    catalog = _catalog()
    gemini_key = (
        settings.gemini_api_key.get_secret_value() if settings.gemini_api_key is not None else ""
    )
    tavily_key = (
        settings.tavily_api_key.get_secret_value() if settings.tavily_api_key is not None else ""
    )
    researcher: AiResearcher
    embedding_provider: EmbeddingProvider
    answer_generator: ConsumerAnswerGenerator
    google_search: GoogleGroundedSearch | None = None
    tavily_search: TavilyWebSearch | None = None
    organization_resolver: WikidataOrganizationResolver | None = None
    if gemini_key:
        search_providers: list[PublicWebSearchProvider] = []
        if settings.google_grounding_enabled:
            google_search = GoogleGroundedSearch(
                gemini_key,
                settings.gemini_search_model,
                settings.gemini_timeout_seconds,
            )
            search_providers.append(google_search)
        tavily_search = TavilyWebSearch(
            tavily_key or None,
            settings.tavily_base_url,
            settings.tavily_timeout_seconds,
        )
        search_providers.append(tavily_search)
        organization_resolver = WikidataOrganizationResolver(
            settings.wikidata_base_url,
            settings.open_food_facts_user_agent,
            settings.wikidata_timeout_seconds,
        )
        researcher = GeminiEvidenceResearcher(
            gemini_key,
            settings.gemini_model,
            CompositeWebSearch(search_providers),
            settings.gemini_timeout_seconds,
            organization_resolver=organization_resolver,
        )
    else:
        researcher = UnavailableResearcher(
            settings.gemini_model,
            "Add GEMINI_API_KEY to .env to synthesize public-source research.",
        )

    if gemini_key:
        embedding_provider = GeminiEmbeddingProvider(
            gemini_key,
            settings.gemini_embedding_model,
            settings.gemini_embedding_dimensions,
            settings.gemini_timeout_seconds,
        )
        answer_generator = GeminiConsumerAnswerGenerator(
            gemini_key,
            settings.gemini_model,
            settings.gemini_timeout_seconds,
        )
    else:
        embedding_provider = UnavailableEmbeddingProvider(
            settings.gemini_embedding_model,
            settings.gemini_embedding_dimensions,
        )
        answer_generator = UnavailableAnswerGenerator(settings.gemini_model)
    try:
        yield ConsumerResearchService(
            catalog,
            SqlAlchemyConsumerEvidenceRepository(session),
            researcher,
            embedding_provider,
            LangChainConsumerRag(answer_generator),
            ttl_days=settings.ai_research_ttl_days,
            catalog_cache_ttl_hours=settings.catalog_cache_ttl_hours,
        )
    finally:
        if tavily_search is not None:
            tavily_search.close()
        if organization_resolver is not None:
            organization_resolver.close()
        catalog.close()


def _catalog() -> FallbackProductCatalog:
    settings = get_settings()
    open_food_facts = OpenFoodFactsCatalog(
        base_url=settings.open_food_facts_base_url,
        user_agent=settings.open_food_facts_user_agent,
        timeout_seconds=settings.open_food_facts_timeout_seconds,
    )
    usda_key = settings.usda_api_key.get_secret_value() if settings.usda_api_key else ""
    usda = (
        UsdaFoodDataCatalog(
            usda_key,
            settings.usda_base_url,
            settings.usda_timeout_seconds,
        )
        if usda_key
        else None
    )
    return FallbackProductCatalog(open_food_facts, usda)
