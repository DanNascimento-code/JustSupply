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
    UnavailableAnswerGenerator,
    UnavailableEmbeddingProvider,
    UnavailableResearcher,
)
from justsupply.integrations.gemini import (
    GeminiConsumerAnswerGenerator,
    GeminiEmbeddingProvider,
    GeminiWebResearcher,
)
from justsupply.integrations.langchain_rag import LangChainConsumerRag
from justsupply.integrations.open_food_facts import OpenFoodFactsCatalog
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.services.consumer import ConsumerResearchService, ConsumerService


def get_consumer_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> Iterator[ConsumerService]:
    catalog = _catalog()
    try:
        yield ConsumerService(catalog, SqlAlchemyConsumerEvidenceRepository(session))
    finally:
        catalog.close()


def get_consumer_research_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> Iterator[ConsumerResearchService]:
    settings = get_settings()
    catalog = _catalog()
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key is not None else ""
    researcher: AiResearcher
    embedding_provider: EmbeddingProvider
    answer_generator: ConsumerAnswerGenerator
    if key:
        researcher = GeminiWebResearcher(key, settings.gemini_model)
        embedding_provider = GeminiEmbeddingProvider(
            key,
            settings.gemini_embedding_model,
            settings.gemini_embedding_dimensions,
        )
        answer_generator = GeminiConsumerAnswerGenerator(key, settings.gemini_model)
    else:
        researcher = UnavailableResearcher(settings.gemini_model)
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
        )
    finally:
        catalog.close()


def _catalog() -> OpenFoodFactsCatalog:
    settings = get_settings()
    return OpenFoodFactsCatalog(
        base_url=settings.open_food_facts_base_url,
        user_agent=settings.open_food_facts_user_agent,
        timeout_seconds=settings.open_food_facts_timeout_seconds,
    )
