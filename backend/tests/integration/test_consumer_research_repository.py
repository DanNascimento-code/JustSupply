import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from justsupply.database.models import EvidenceSourceModel, ProductModel
from justsupply.database.session import SessionFactory
from justsupply.domain.research import AiResearchResult, GroundedWebSource
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.schemas.consumer import (
    AiResearchAssessment,
    AiResearchTranslations,
    AssessmentDimension,
    AssessmentStatus,
    EvidenceScope,
    LocalizedAssessmentText,
    UserLocale,
)
from justsupply.services.consumer import ConsumerService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="Set RUN_DATABASE_TESTS=1 to run PostgreSQL integration tests.",
    ),
]


class FixedCatalog:
    def __init__(self, product: CatalogProduct) -> None:
        self.product = product

    def search(self, query: str) -> list[CatalogProduct]:
        del query
        return [self.product]


def translations(portuguese: str, spanish: str) -> AiResearchTranslations:
    return AiResearchTranslations(
        pt_br=LocalizedAssessmentText(finding=portuguese),
        es_latam=LocalizedAssessmentText(finding=spanish),
    )


def test_research_is_persisted_and_retrieved_by_vector_similarity() -> None:
    suffix = uuid4().hex[:12]
    barcode = str(uuid4().int % 10**13).zfill(13)
    product = CatalogProduct(
        barcode=barcode,
        name=f"Consumer product {suffix}",
        brand=f"Consumer brand {suffix}",
        image_url=None,
        ingredients_analysis_tags=frozenset({"en:vegan"}),
        environmental_score_grade="b",
        last_updated_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
        source_url=f"https://world.openfoodfacts.org/product/{barcode}",
    )
    source_urls = [
        f"https://example.org/certification/{suffix}",
        f"https://ngo.example/reports/{suffix}",
    ]
    result = AiResearchResult(
        provider_response_id="research-test",
        searched_at=datetime.now(UTC),
        sources=[
            GroundedWebSource(
                number=1,
                title="Certification registry",
                provider_name="example.org",
                url=source_urls[0],
                cited_text="The registry lists the product as vegan certified.",
            ),
            GroundedWebSource(
                number=2,
                title="Independent employment report",
                provider_name="ngo.example",
                url=source_urls[1],
                cited_text="The report describes workforce representation and leadership.",
            ),
        ],
        assessments=[
            AiResearchAssessment(
                dimension=AssessmentDimension.VEGAN_COMPOSITION,
                status=AssessmentStatus.SUPPORTED,
                finding="A registry lists the product as vegan certified.",
                evidence_scope=EvidenceScope.PRODUCT,
                source_numbers=[1],
                translations=translations(
                    "Um registro lista o produto como vegano certificado.",
                    "Un registro lista el producto como vegano certificado.",
                ),
            ),
            AiResearchAssessment(
                dimension=AssessmentDimension.ENVIRONMENTAL_IMPACT,
                status=AssessmentStatus.UNKNOWN,
                finding="No product-specific lifecycle evidence was found.",
                evidence_scope=EvidenceScope.PRODUCT,
                source_numbers=[],
                translations=translations(
                    "Nenhuma evidência de ciclo de vida foi encontrada.",
                    "No se encontró evidencia del ciclo de vida.",
                ),
            ),
            AiResearchAssessment(
                dimension=AssessmentDimension.WOMEN_WORKERS,
                status=AssessmentStatus.SUPPORTED,
                finding="An independent report describes workforce representation.",
                evidence_scope=EvidenceScope.BRAND,
                source_numbers=[2],
                translations=translations(
                    "Um relatório independente descreve a representação.",
                    "Un informe independiente describe la representación.",
                ),
            ),
            AiResearchAssessment(
                dimension=AssessmentDimension.MINORITY_INCLUSION,
                status=AssessmentStatus.NOT_DISCLOSED,
                finding="No direct public disclosure was found.",
                evidence_scope=EvidenceScope.BRAND,
                source_numbers=[],
                translations=translations(
                    "Nenhuma divulgação pública direta foi encontrada.",
                    "No se encontró una divulgación pública directa.",
                ),
            ),
        ],
    )
    first_embedding = [0.0] * 1536
    first_embedding[0] = 1.0
    second_embedding = [0.0] * 1536
    second_embedding[1] = 1.0

    with SessionFactory() as session:
        repository = SqlAlchemyConsumerEvidenceRepository(session)
        ConsumerService(FixedCatalog(product), repository).search(barcode)
        stored = repository.save_research(
            barcode,
            result,
            model_name="gemini-test",
            prompt_version="consumer-web-research-v1",
            embeddings=[first_embedding, second_embedding],
            embedding_model="gemini-embedding-test",
            embedding_dimensions=1536,
            ttl_days=7,
        )

        assert stored.metadata.source_count == 2
        assert stored.assessments[AssessmentDimension.WOMEN_WORKERS].verification == (
            "single_source"
        )
        portuguese = repository.get_research(barcode, UserLocale.PORTUGUESE_BRAZIL)
        assert portuguese is not None
        assert portuguese.assessments[AssessmentDimension.WOMEN_WORKERS].finding.startswith(
            "Um relatório"
        )
        retrieved = repository.search_evidence(
            barcode,
            first_embedding,
            embedding_model="gemini-embedding-test",
            embedding_dimensions=1536,
            top_k=2,
        )
        assert retrieved[0].title == "Certification registry"
        assert retrieved[0].similarity == pytest.approx(1.0)

        stored_product = session.scalar(select(ProductModel).where(ProductModel.barcode == barcode))
        assert stored_product is not None
        session.execute(delete(ProductModel).where(ProductModel.id == stored_product.id))
        session.execute(delete(EvidenceSourceModel).where(EvidenceSourceModel.url.in_(source_urls)))
        session.execute(
            delete(EvidenceSourceModel).where(EvidenceSourceModel.url == product.source_url)
        )
        session.commit()
