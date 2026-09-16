from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from justsupply.database.models import (
    BrandModel,
    ClaimEvidenceRecordModel,
    ClaimModel,
    EvidenceRecordModel,
    EvidenceSourceModel,
)
from justsupply.repositories.consumer_evidence import EvidencePersistenceError
from justsupply.schemas.brand_evidence import (
    BrandClaimRead,
    BrandEvidenceCreate,
    BrandSummaryRead,
    ReviewDecision,
    ReviewStatus,
)
from justsupply.schemas.consumer import AssessmentDimension, AssessmentSourceRead, AssessmentStatus


class BrandNotFoundError(Exception):
    def __init__(self, brand_id: UUID) -> None:
        super().__init__(f"Brand '{brand_id}' was not found.")


class BrandClaimNotFoundError(Exception):
    def __init__(self, claim_id: UUID) -> None:
        super().__init__(f"Brand claim '{claim_id}' was not found.")


class SqlAlchemyBrandEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_brands(self) -> list[BrandSummaryRead]:
        brands = self._session.scalars(select(BrandModel).order_by(BrandModel.name.asc())).all()
        return [BrandSummaryRead(id=brand.id, name=brand.name) for brand in brands]

    def list_claims(self, brand_id: UUID) -> list[BrandClaimRead]:
        brand = self._get_brand(brand_id)
        claims = self._session.scalars(
            select(ClaimModel)
            .where(
                ClaimModel.brand_id == brand.id,
                ClaimModel.origin == "manual",
            )
            .order_by(ClaimModel.updated_at.desc())
        ).all()
        return [self._to_read(claim, brand) for claim in claims]

    def create_claim(
        self,
        brand_id: UUID,
        payload: BrandEvidenceCreate,
    ) -> BrandClaimRead:
        brand = self._get_brand(brand_id)
        now = datetime.now(UTC)

        try:
            source = self._upsert_source(payload, now)
            self._session.flush()
            claim = self._upsert_claim(brand, payload, now)
            evidence = self._upsert_evidence(source, payload, now)
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
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError("The brand evidence could not be saved.") from error

        return self._to_read(claim, brand)

    def review_claim(
        self,
        claim_id: UUID,
        decision: ReviewDecision,
    ) -> BrandClaimRead:
        claim = self._session.get(ClaimModel, claim_id)
        if claim is None or claim.origin != "manual" or claim.brand_id is None:
            raise BrandClaimNotFoundError(claim_id)

        brand = self._get_brand(claim.brand_id)
        claim.review_status = decision.value
        claim.reviewed_at = datetime.now(UTC)
        claim.updated_at = claim.reviewed_at
        self._session.commit()
        return self._to_read(claim, brand)

    def _get_brand(self, brand_id: UUID) -> BrandModel:
        brand = self._session.get(BrandModel, brand_id)
        if brand is None:
            raise BrandNotFoundError(brand_id)
        return brand

    def _upsert_source(
        self,
        payload: BrandEvidenceCreate,
        now: datetime,
    ) -> EvidenceSourceModel:
        source_url = str(payload.source_url)
        url_key = _fingerprint(source_url)
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

        source.provider_name = payload.source_provider
        source.title = payload.source_title
        source.url = source_url
        source.source_type = payload.source_type.value
        source.published_at = payload.published_at
        source.retrieved_at = now
        source.updated_at = now
        return source

    def _upsert_claim(
        self,
        brand: BrandModel,
        payload: BrandEvidenceCreate,
        now: datetime,
    ) -> ClaimModel:
        claim = self._session.scalar(
            select(ClaimModel).where(
                ClaimModel.brand_id == brand.id,
                ClaimModel.dimension == payload.dimension.value,
            )
        )
        if claim is None:
            claim = ClaimModel(
                id=uuid4(),
                subject_scope="brand",
                product_id=None,
                brand_id=brand.id,
                dimension=payload.dimension.value,
                created_at=now,
                updated_at=now,
            )
            self._session.add(claim)

        claim.status = payload.status.value
        claim.statement = payload.statement
        claim.origin = "manual"
        claim.review_status = "pending"
        claim.reviewed_at = None
        claim.updated_at = now
        return claim

    def _upsert_evidence(
        self,
        source: EvidenceSourceModel,
        payload: BrandEvidenceCreate,
        now: datetime,
    ) -> EvidenceRecordModel:
        fingerprint = _fingerprint(
            "\0".join(
                (
                    payload.dimension.value,
                    payload.status.value,
                    payload.statement,
                    payload.excerpt or "",
                    payload.source_location or "",
                )
            )
        )
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
                summary=payload.statement,
                excerpt=payload.excerpt,
                source_location=payload.source_location,
                observed_at=payload.published_at,
                collected_at=now,
                created_at=now,
            )
            self._session.add(evidence)
        return evidence

    def _to_read(self, claim: ClaimModel, brand: BrandModel) -> BrandClaimRead:
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
        return BrandClaimRead(
            id=claim.id,
            brand_id=brand.id,
            brand_name=brand.name,
            dimension=AssessmentDimension(claim.dimension),
            status=AssessmentStatus(claim.status),
            statement=claim.statement,
            review_status=ReviewStatus(claim.review_status),
            reviewed_at=claim.reviewed_at,
            created_at=claim.created_at,
            updated_at=claim.updated_at,
            sources=[
                AssessmentSourceRead(
                    title=source.title,
                    provider_name=source.provider_name,
                    url=source.url,
                    published_at=source.published_at,
                    source_location=source_location,
                )
                for source, source_location in source_rows
            ],
        )


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
