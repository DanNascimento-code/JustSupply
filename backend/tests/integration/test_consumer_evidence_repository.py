import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select

from justsupply.database.models import (
    BrandModel,
    ClaimEvidenceRecordModel,
    ClaimModel,
    EvidenceRecordModel,
    EvidenceSourceModel,
    ProductModel,
)
from justsupply.database.session import SessionFactory
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.repositories.brand_evidence import SqlAlchemyBrandEvidenceRepository
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.schemas.brand_evidence import (
    BrandEvidenceCreate,
    EvidenceSourceType,
    ReviewDecision,
)
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus
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
        self._product = product

    def search(self, query: str) -> list[CatalogProduct]:
        del query
        return [self._product]


def test_consumer_search_persists_evidence_without_duplicates() -> None:
    unique_suffix = uuid4().hex[:12]
    barcode = str(uuid4().int % 10**13).zfill(13)
    product = CatalogProduct(
        barcode=barcode,
        name=f"Evidence test product {unique_suffix}",
        brand=f"Evidence test brand {unique_suffix}",
        image_url=None,
        ingredients_analysis_tags=frozenset({"en:vegan"}),
        environmental_score_grade="c",
        last_updated_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        source_url=f"https://world.openfoodfacts.org/product/{barcode}",
    )

    with SessionFactory() as session:
        repository = SqlAlchemyConsumerEvidenceRepository(session)
        service = ConsumerService(FixedCatalog(product), repository)

        service.search(barcode)
        service.search(barcode)

        stored_product = session.scalar(select(ProductModel).where(ProductModel.barcode == barcode))
        assert stored_product is not None
        assert stored_product.name == product.name

        stored_brand = session.get(BrandModel, stored_product.brand_id)
        assert stored_brand is not None
        assert stored_brand.name == product.brand

        source = session.scalar(
            select(EvidenceSourceModel).where(EvidenceSourceModel.url == product.source_url)
        )
        assert source is not None

        claims = session.scalars(
            select(ClaimModel).where(
                or_(
                    ClaimModel.product_id == stored_product.id,
                    ClaimModel.brand_id == stored_brand.id,
                )
            )
        ).all()
        assert len(claims) == 4
        assert {claim.dimension: claim.status for claim in claims} == {
            "vegan_composition": "supported",
            "environmental_impact": "mixed",
            "women_workers": "not_disclosed",
            "minority_inclusion": "not_disclosed",
        }

        evidence_records = session.scalars(
            select(EvidenceRecordModel).where(EvidenceRecordModel.source_id == source.id)
        ).all()
        assert len(evidence_records) == 2

        relationships = session.scalars(
            select(ClaimEvidenceRecordModel).where(
                ClaimEvidenceRecordModel.evidence_record_id.in_(
                    evidence.id for evidence in evidence_records
                )
            )
        ).all()
        assert len(relationships) == 2

        session.execute(delete(EvidenceSourceModel).where(EvidenceSourceModel.id == source.id))
        session.execute(delete(ProductModel).where(ProductModel.id == stored_product.id))
        session.execute(delete(BrandModel).where(BrandModel.id == stored_brand.id))
        session.commit()


def test_approved_social_evidence_is_published_to_consumer() -> None:
    unique_suffix = uuid4().hex[:12]
    barcode = str(uuid4().int % 10**13).zfill(13)
    manual_source_url = f"https://example.org/reports/{unique_suffix}"
    product = CatalogProduct(
        barcode=barcode,
        name=f"Review test product {unique_suffix}",
        brand=f"Review test brand {unique_suffix}",
        image_url=None,
        ingredients_analysis_tags=frozenset({"en:vegan"}),
        environmental_score_grade="c",
        last_updated_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        source_url=f"https://world.openfoodfacts.org/product/{barcode}",
    )

    with SessionFactory() as session:
        consumer_repository = SqlAlchemyConsumerEvidenceRepository(session)
        consumer_service = ConsumerService(FixedCatalog(product), consumer_repository)
        consumer_service.search(barcode)

        stored_product = session.scalar(select(ProductModel).where(ProductModel.barcode == barcode))
        assert stored_product is not None
        assert stored_product.brand_id is not None

        brand_repository = SqlAlchemyBrandEvidenceRepository(session)
        claim = brand_repository.create_claim(
            stored_product.brand_id,
            BrandEvidenceCreate(
                dimension=AssessmentDimension.WOMEN_WORKERS,
                status=AssessmentStatus.SUPPORTED,
                statement="The report documents a leadership program for women workers.",
                source_title="2025 Impact Report",
                source_provider="Example Organization",
                source_url=manual_source_url,
                source_type=EvidenceSourceType.CORPORATE_REPORT,
                excerpt="The program includes leadership training and promotion targets.",
                source_location="page 18",
                published_at=datetime(2025, 12, 1, tzinfo=UTC),
            ),
        )
        assert claim.review_status == "pending"

        pending_result = consumer_service.search(barcode)
        assert pending_result.items[0].assessments[2].status == AssessmentStatus.NOT_DISCLOSED

        approved_claim = brand_repository.review_claim(claim.id, ReviewDecision.APPROVED)
        assert approved_claim.review_status == "approved"

        published_result = consumer_service.search(barcode)
        women_assessment = published_result.items[0].assessments[2]
        assert women_assessment.status == AssessmentStatus.SUPPORTED
        assert women_assessment.sources[0].provider_name == "Example Organization"
        assert published_result.items[0].evidence_coverage_percent == 75

        session.execute(
            delete(EvidenceSourceModel).where(
                EvidenceSourceModel.url.in_([product.source_url, manual_source_url])
            )
        )
        session.execute(delete(ProductModel).where(ProductModel.id == stored_product.id))
        session.execute(delete(BrandModel).where(BrandModel.id == stored_product.brand_id))
        session.commit()
