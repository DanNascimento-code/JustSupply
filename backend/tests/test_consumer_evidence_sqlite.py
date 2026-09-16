from datetime import UTC, datetime

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session

from justsupply.database.models import (
    BrandModel,
    ClaimEvidenceRecordModel,
    ClaimModel,
    EvidenceRecordModel,
    EvidenceSourceModel,
    ProductModel,
)
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.services.consumer import ConsumerService


class FixedCatalog:
    def __init__(self, product: CatalogProduct) -> None:
        self._product = product

    def search(self, query: str) -> list[CatalogProduct]:
        del query
        return [self._product]


def test_catalog_snapshot_is_persisted_idempotently() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    tables = [
        BrandModel.__table__,
        ProductModel.__table__,
        EvidenceSourceModel.__table__,
        ClaimModel.__table__,
        EvidenceRecordModel.__table__,
        ClaimEvidenceRecordModel.__table__,
    ]
    BrandModel.metadata.create_all(engine, tables=tables)
    product = CatalogProduct(
        barcode="7891000100103",
        name="Dark chocolate",
        brand="Example Foods",
        image_url=None,
        ingredients_analysis_tags=frozenset({"en:vegan"}),
        environmental_score_grade="c",
        last_updated_at=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        source_url="https://world.openfoodfacts.org/product/7891000100103",
    )

    with Session(engine) as session:
        service = ConsumerService(
            FixedCatalog(product),
            SqlAlchemyConsumerEvidenceRepository(session),
        )

        service.search(product.barcode)
        service.search(product.barcode)

        stored_product = session.scalar(
            select(ProductModel).where(ProductModel.barcode == product.barcode)
        )
        assert stored_product is not None
        assert stored_product.name == product.name

        stored_brand = session.get(BrandModel, stored_product.brand_id)
        assert stored_brand is not None
        assert stored_brand.name == product.brand

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
        assert len(session.scalars(select(EvidenceSourceModel)).all()) == 1
        assert len(session.scalars(select(EvidenceRecordModel)).all()) == 2
        assert len(session.scalars(select(ClaimEvidenceRecordModel)).all()) == 2
