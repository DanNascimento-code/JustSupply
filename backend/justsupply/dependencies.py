from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from justsupply.core.config import get_settings
from justsupply.database.session import get_database_session
from justsupply.integrations.ai import (
    EvidenceExtractor,
    UnavailableAnswerGenerator,
    UnavailableEmbeddingProvider,
    UnavailableEvidenceExtractor,
)
from justsupply.integrations.celery_dispatcher import CeleryDocumentJobDispatcher
from justsupply.integrations.gemini import (
    GeminiEmbeddingProvider,
    GeminiEvidenceExtractor,
    GeminiGroundedAnswerGenerator,
)
from justsupply.integrations.langchain_rag import LangChainRagOrchestrator
from justsupply.integrations.open_food_facts import OpenFoodFactsCatalog
from justsupply.integrations.openai_extractor import OpenAIEvidenceExtractor
from justsupply.integrations.openai_rag import (
    OpenAIEmbeddingProvider,
    OpenAIGroundedAnswerGenerator,
)
from justsupply.repositories.brand_evidence import SqlAlchemyBrandEvidenceRepository
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.repositories.document_ingestion import SqlAlchemyDocumentRepository
from justsupply.repositories.rag import SqlAlchemyRagRepository
from justsupply.repositories.supplier import SqlAlchemySupplierRepository
from justsupply.services.brand_evidence import BrandEvidenceService
from justsupply.services.consumer import ConsumerService
from justsupply.services.document_ingestion import (
    DocumentIngestionProcessor,
    DocumentIngestionService,
)
from justsupply.services.rag import (
    AnswerGenerator,
    EmbeddingProvider,
    RagIndexingService,
    RagRetriever,
    RagService,
)
from justsupply.services.supplier import SupplierService


def get_supplier_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> SupplierService:
    repository = SqlAlchemySupplierRepository(session)
    return SupplierService(repository)


def get_consumer_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> Iterator[ConsumerService]:
    settings = get_settings()
    catalog = OpenFoodFactsCatalog(
        base_url=settings.open_food_facts_base_url,
        user_agent=settings.open_food_facts_user_agent,
        timeout_seconds=settings.open_food_facts_timeout_seconds,
    )
    evidence_repository = SqlAlchemyConsumerEvidenceRepository(session)
    try:
        yield ConsumerService(catalog, evidence_repository)
    finally:
        catalog.close()


def get_brand_evidence_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> BrandEvidenceService:
    return BrandEvidenceService(SqlAlchemyBrandEvidenceRepository(session))


def get_document_ingestion_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> DocumentIngestionService:
    settings = get_settings()
    return DocumentIngestionService(
        SqlAlchemyDocumentRepository(session),
        CeleryDocumentJobDispatcher(),
        upload_directory=Path(settings.document_upload_directory),
        max_bytes=settings.document_max_bytes,
    )


def build_document_ingestion_processor(session: Session) -> DocumentIngestionProcessor:
    settings = get_settings()
    embedding_provider = get_configured_embedding_provider()
    return DocumentIngestionProcessor(
        SqlAlchemyDocumentRepository(session),
        _get_evidence_extractor(),
        RagIndexingService(
            embedding_provider,
            target_characters=settings.rag_chunk_target_characters,
            overlap_characters=settings.rag_chunk_overlap_characters,
        ),
        upload_directory=Path(settings.document_upload_directory),
        max_bytes=settings.document_max_bytes,
        max_characters=settings.document_max_characters,
    )


def get_rag_service(
    session: Annotated[Session, Depends(get_database_session)],
) -> RagService:
    settings = get_settings()
    repository = SqlAlchemyRagRepository(session)
    embedding_provider = get_configured_embedding_provider()
    retriever = RagRetriever(repository, embedding_provider)
    answer_generator = _get_answer_generator()
    indexer = RagIndexingService(
        embedding_provider,
        target_characters=settings.rag_chunk_target_characters,
        overlap_characters=settings.rag_chunk_overlap_characters,
    )
    return RagService(
        repository,
        retriever,
        LangChainRagOrchestrator(retriever, answer_generator),
        indexer,
    )


def get_configured_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.ai_provider == "gemini":
        if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
            return UnavailableEmbeddingProvider(
                settings.gemini_embedding_model,
                settings.gemini_embedding_dimensions,
            )
        return GeminiEmbeddingProvider(
            settings.gemini_api_key.get_secret_value(),
            settings.gemini_embedding_model,
            settings.gemini_embedding_dimensions,
        )

    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        return UnavailableEmbeddingProvider(
            settings.openai_embedding_model,
            settings.openai_embedding_dimensions,
        )
    return OpenAIEmbeddingProvider(
        settings.openai_api_key.get_secret_value(),
        settings.openai_embedding_model,
        settings.openai_embedding_dimensions,
    )


def _get_answer_generator() -> AnswerGenerator:
    settings = get_settings()
    if settings.ai_provider == "gemini":
        if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
            return UnavailableAnswerGenerator(settings.gemini_model)
        return GeminiGroundedAnswerGenerator(
            settings.gemini_api_key.get_secret_value(),
            settings.gemini_model,
        )

    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        return UnavailableAnswerGenerator(settings.openai_model)
    return OpenAIGroundedAnswerGenerator(
        settings.openai_api_key.get_secret_value(),
        settings.openai_model,
    )


def _get_evidence_extractor() -> EvidenceExtractor:
    settings = get_settings()
    if settings.ai_provider == "gemini":
        if settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value():
            return UnavailableEvidenceExtractor(settings.gemini_model)
        return GeminiEvidenceExtractor(
            settings.gemini_api_key.get_secret_value(),
            settings.gemini_model,
        )

    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        return UnavailableEvidenceExtractor(settings.openai_model)
    return OpenAIEvidenceExtractor(
        settings.openai_api_key.get_secret_value(),
        settings.openai_model,
    )
