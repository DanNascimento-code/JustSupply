from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    ConsumerAssessment,
    ConsumerProductRead,
    EvidenceScope,
)

AssessedCatalogProduct = tuple[CatalogProduct, ConsumerProductRead]


class EvidencePersistenceError(Exception):
    """Raised when an evidence snapshot cannot be persisted."""


class ConsumerEvidenceRepository(Protocol):
    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None: ...

    def approved_brand_assessments(
        self,
        brand_names: str | None,
    ) -> dict[AssessmentDimension, ConsumerAssessment]: ...


class NullConsumerEvidenceRepository:
    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        del products

    def approved_brand_assessments(
        self,
        brand_names: str | None,
    ) -> dict[AssessmentDimension, ConsumerAssessment]:
        del brand_names
        return {}


class SqlAlchemyConsumerEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        now = datetime.now(UTC)
        try:
            for catalog_product, assessed_product in products:
                brand = self._upsert_brand(catalog_product.brand, now)
                # UUID foreign keys are assigned directly rather than through
                # ORM relationships, so each dependency layer is flushed in
                # order before the next layer references it.
                self._session.flush()
                product = self._upsert_product(catalog_product, brand, now)
                source = self._upsert_source(catalog_product, now)
                self._session.flush()
                self._upsert_claims(assessed_product, product, brand, source, now)
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError(
                "The product evidence snapshot could not be saved."
            ) from error

    def approved_brand_assessments(
        self,
        brand_names: str | None,
    ) -> dict[AssessmentDimension, ConsumerAssessment]:
        brand_name = _primary_brand_name(brand_names)
        if brand_name is None:
            return {}

        brand = self._session.scalar(
            select(BrandModel).where(BrandModel.name_key == brand_name.casefold())
        )
        if brand is None:
            return {}

        claims = self._session.scalars(
            select(ClaimModel).where(
                ClaimModel.brand_id == brand.id,
                ClaimModel.origin == "manual",
                ClaimModel.review_status == "approved",
            )
        ).all()

        assessments: dict[AssessmentDimension, ConsumerAssessment] = {}
        for claim in claims:
            try:
                dimension = AssessmentDimension(claim.dimension)
                finding_status = AssessmentStatus(claim.status)
            except ValueError:
                continue

            source_rows = self._session.execute(
                select(EvidenceSourceModel, EvidenceRecordModel.source_location)
                .join(
                    EvidenceRecordModel,
                    EvidenceRecordModel.source_id == EvidenceSourceModel.id,
                )
                .join(
                    ClaimEvidenceRecordModel,
                    ClaimEvidenceRecordModel.evidence_record_id == EvidenceRecordModel.id,
                )
                .where(ClaimEvidenceRecordModel.claim_id == claim.id)
            ).all()
            sources = [
                AssessmentSourceRead(
                    title=source.title,
                    provider_name=source.provider_name,
                    url=source.url,
                    published_at=source.published_at,
                    source_location=source_location,
                )
                for source, source_location in source_rows
            ]
            assessments[dimension] = ConsumerAssessment(
                dimension=dimension,
                title=_dimension_title(dimension),
                status=finding_status,
                finding=claim.statement,
                evidence_scope=EvidenceScope.BRAND,
                sources=sources,
            )
        return assessments

    def _upsert_brand(self, brand_names: str | None, now: datetime) -> BrandModel | None:
        brand_name = _primary_brand_name(brand_names)
        if brand_name is None:
            return None

        name_key = brand_name.casefold()
        brand = self._session.scalar(select(BrandModel).where(BrandModel.name_key == name_key))
        if brand is None:
            brand = BrandModel(
                id=uuid4(),
                name=brand_name,
                name_key=name_key,
                created_at=now,
                updated_at=now,
            )
            self._session.add(brand)
        else:
            brand.name = brand_name
            brand.updated_at = now
        return brand

    def _upsert_product(
        self,
        catalog_product: CatalogProduct,
        brand: BrandModel | None,
        now: datetime,
    ) -> ProductModel:
        product = self._session.scalar(
            select(ProductModel).where(ProductModel.barcode == catalog_product.barcode)
        )
        if product is None:
            product = ProductModel(
                id=uuid4(),
                barcode=catalog_product.barcode,
                created_at=now,
                updated_at=now,
            )
            self._session.add(product)

        product.name = catalog_product.name
        product.brand_id = brand.id if brand is not None else None
        product.image_url = catalog_product.image_url
        product.catalog_updated_at = catalog_product.last_updated_at
        product.updated_at = now
        return product

    def _upsert_source(
        self,
        catalog_product: CatalogProduct,
        now: datetime,
    ) -> EvidenceSourceModel:
        url_key = _fingerprint(catalog_product.source_url)
        source = self._session.scalar(
            select(EvidenceSourceModel).where(EvidenceSourceModel.url_key == url_key)
        )
        if source is None:
            source = EvidenceSourceModel(
                id=uuid4(),
                url_key=url_key,
                created_at=now,
                updated_at=now,
            )
            self._session.add(source)

        source.provider_name = "Open Food Facts"
        source.title = f"{catalog_product.name} — Open Food Facts"
        source.url = catalog_product.source_url
        source.source_type = "public_database"
        source.published_at = catalog_product.last_updated_at
        source.retrieved_at = now
        source.updated_at = now
        return source

    def _upsert_claims(
        self,
        assessed_product: ConsumerProductRead,
        product: ProductModel,
        brand: BrandModel | None,
        source: EvidenceSourceModel,
        now: datetime,
    ) -> None:
        for assessment in assessed_product.assessments:
            if assessment.evidence_scope == EvidenceScope.BRAND and brand is None:
                continue

            claim = self._find_claim(
                product=product,
                brand=brand,
                scope=assessment.evidence_scope,
                dimension=assessment.dimension.value,
            )
            if claim is None:
                claim = ClaimModel(
                    id=uuid4(),
                    subject_scope=assessment.evidence_scope.value,
                    product_id=(
                        product.id if assessment.evidence_scope == EvidenceScope.PRODUCT else None
                    ),
                    brand_id=(
                        brand.id
                        if brand is not None and assessment.evidence_scope == EvidenceScope.BRAND
                        else None
                    ),
                    dimension=assessment.dimension.value,
                    origin="catalog",
                    review_status="not_required",
                    reviewed_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(claim)
            elif claim.origin == "manual":
                # A public catalog cannot overwrite evidence submitted and
                # reviewed by a human analyst.
                continue

            claim.status = assessment.status.value
            claim.statement = assessment.finding
            claim.updated_at = now

            if assessment.status in {
                AssessmentStatus.SUPPORTED,
                AssessmentStatus.MIXED,
                AssessmentStatus.CONCERN,
            }:
                self._link_evidence(claim, source, assessment.finding, assessed_product, now)

    def _find_claim(
        self,
        *,
        product: ProductModel,
        brand: BrandModel | None,
        scope: EvidenceScope,
        dimension: str,
    ) -> ClaimModel | None:
        statement = select(ClaimModel).where(ClaimModel.dimension == dimension)
        if scope == EvidenceScope.PRODUCT:
            statement = statement.where(ClaimModel.product_id == product.id)
        elif brand is not None:
            statement = statement.where(ClaimModel.brand_id == brand.id)
        return self._session.scalar(statement)

    def _link_evidence(
        self,
        claim: ClaimModel,
        source: EvidenceSourceModel,
        summary: str,
        assessed_product: ConsumerProductRead,
        now: datetime,
    ) -> None:
        fingerprint = _fingerprint(f"{claim.dimension}\0{claim.status}\0{summary}")
        evidence = self._session.scalar(
            select(EvidenceRecordModel).where(
                EvidenceRecordModel.source_id == source.id,
                EvidenceRecordModel.fingerprint == fingerprint,
            )
        )
        if evidence is None:
            evidence = EvidenceRecordModel(
                id=uuid4(),
                source_id=source.id,
                fingerprint=fingerprint,
                summary=summary,
                excerpt=None,
                source_location=None,
                observed_at=assessed_product.last_updated_at,
                collected_at=now,
                created_at=now,
            )
            self._session.add(evidence)

        # The link stores UUIDs rather than ORM object relationships. Flush the
        # referenced claim and evidence first so PostgreSQL can enforce both
        # foreign keys when the link is inserted.
        self._session.flush()
        relationship = self._session.get(
            ClaimEvidenceRecordModel,
            (claim.id, evidence.id),
        )
        if relationship is None:
            self._session.add(
                ClaimEvidenceRecordModel(
                    claim_id=claim.id,
                    evidence_record_id=evidence.id,
                    relationship="supports",
                )
            )


def _primary_brand_name(brand_names: str | None) -> str | None:
    if brand_names is None:
        return None
    primary_name = brand_names.split(",", maxsplit=1)[0].strip()
    return primary_name or None


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _dimension_title(dimension: AssessmentDimension) -> str:
    titles = {
        AssessmentDimension.VEGAN_COMPOSITION: "Vegan composition",
        AssessmentDimension.ENVIRONMENTAL_IMPACT: "Environmental impact",
        AssessmentDimension.WOMEN_WORKERS: "Women workers",
        AssessmentDimension.MINORITY_INCLUSION: "Minority inclusion",
    }
    return titles[dimension]
