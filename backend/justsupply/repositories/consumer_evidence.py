from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from justsupply.database.models import (
    AiResearchRunModel,
    BrandModel,
    ClaimEvidenceRecordModel,
    ClaimModel,
    EvidenceRecordModel,
    EvidenceSourceModel,
    ProductModel,
)
from justsupply.domain.research import AiResearchResult, RetrievedEvidence
from justsupply.integrations.open_food_facts import CatalogProduct
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    ConsumerAssessment,
    ConsumerProductRead,
    EvidenceScope,
    ProductResearchMetadata,
    UserLocale,
    VerificationLevel,
)

AssessedCatalogProduct = tuple[CatalogProduct, ConsumerProductRead]


class EvidencePersistenceError(RuntimeError):
    pass


class ProductNotFoundError(Exception):
    def __init__(self, barcode: str) -> None:
        super().__init__(f"Product '{barcode}' was not found in the local evidence index.")


@dataclass(frozen=True)
class StoredResearch:
    assessments: dict[AssessmentDimension, ConsumerAssessment]
    metadata: ProductResearchMetadata
    fresh: bool


class SqlAlchemyConsumerEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        now = datetime.now(UTC)
        try:
            for catalog_product, assessed_product in products:
                brand = self._upsert_brand(catalog_product.brand, now)
                self._session.flush()
                product = self._upsert_product(catalog_product, brand, now)
                source = self._upsert_catalog_source(catalog_product, now)
                self._session.flush()
                self._upsert_catalog_claims(assessed_product, product, brand, source, now)
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError(
                "The product evidence snapshot could not be saved."
            ) from error

    def get_research(
        self,
        barcode: str,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> StoredResearch | None:
        product = self._get_product(barcode)
        run = self._latest_research_run(product.id)
        if run is None:
            return None
        claims = self._session.scalars(
            select(ClaimModel).where(
                (ClaimModel.product_id == product.id)
                | ((ClaimModel.brand_id == product.brand_id) & (ClaimModel.brand_id.is_not(None))),
                ClaimModel.origin == "ai_research",
            )
        ).all()
        assessments = {
            AssessmentDimension(claim.dimension): self._research_assessment(claim, run.id, language)
            for claim in claims
            if claim.dimension in {item.value for item in AssessmentDimension}
        }
        total_sources = len(
            self._session.scalars(
                select(EvidenceRecordModel.id).where(EvidenceRecordModel.research_run_id == run.id)
            ).all()
        )
        return StoredResearch(
            assessments=assessments,
            metadata=ProductResearchMetadata(
                researched_at=run.searched_at,
                model_name=run.model_name,
                source_count=total_sources,
            ),
            fresh=run.expires_at > datetime.now(UTC),
        )

    def save_research(
        self,
        barcode: str,
        result: AiResearchResult,
        *,
        model_name: str,
        prompt_version: str,
        embeddings: list[list[float]],
        embedding_model: str,
        embedding_dimensions: int,
        ttl_days: int,
    ) -> StoredResearch:
        if len(embeddings) != len(result.sources):
            raise EvidencePersistenceError("Research evidence and embedding counts differ.")
        product = self._get_product(barcode)
        now = datetime.now(UTC)
        run = AiResearchRunModel(
            id=uuid4(),
            product_id=product.id,
            model_name=model_name,
            prompt_version=prompt_version,
            provider_response_id=result.provider_response_id,
            searched_at=result.searched_at,
            expires_at=result.searched_at + timedelta(days=ttl_days),
            created_at=now,
        )
        self._session.add(run)
        self._session.flush()

        evidence_by_number: dict[int, EvidenceRecordModel] = {}
        for source, embedding in zip(result.sources, embeddings, strict=True):
            evidence_source = self._upsert_research_source(source, now)
            self._session.flush()
            evidence = EvidenceRecordModel(
                id=uuid4(),
                research_run_id=run.id,
                source_id=evidence_source.id,
                fingerprint=_fingerprint(f"{run.id}\0{source.url}\0{source.cited_text}"),
                summary=source.cited_text,
                excerpt=source.cited_text,
                source_location="Gemini grounded web research",
                observed_at=None,
                collected_at=now,
                created_at=now,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
                embedding=embedding,
            )
            self._session.add(evidence)
            evidence_by_number[source.number] = evidence
        self._session.flush()

        brand = self._session.get(BrandModel, product.brand_id) if product.brand_id else None
        for assessment in result.assessments:
            claim = self._upsert_research_claim(product, brand, assessment, now)
            self._session.flush()
            self._session.execute(
                delete(ClaimEvidenceRecordModel).where(
                    ClaimEvidenceRecordModel.claim_id == claim.id
                )
            )
            for source_number in assessment.source_numbers:
                linked_evidence = evidence_by_number.get(source_number)
                if linked_evidence is not None:
                    self._session.add(
                        ClaimEvidenceRecordModel(
                            claim_id=claim.id,
                            evidence_record_id=linked_evidence.id,
                            relationship="supports",
                        )
                    )
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError("The AI research could not be saved.") from error
        stored = self.get_research(barcode)
        if stored is None:
            raise EvidencePersistenceError("The saved AI research could not be loaded.")
        return stored

    def search_evidence(
        self,
        barcode: str,
        embedding: list[float],
        *,
        embedding_model: str,
        embedding_dimensions: int,
        top_k: int,
    ) -> list[RetrievedEvidence]:
        product = self._get_product(barcode)
        run = self._latest_research_run(product.id)
        if run is None:
            return []
        distance = EvidenceRecordModel.embedding.cosine_distance(embedding).label("distance")
        rows = self._session.execute(
            select(EvidenceRecordModel, EvidenceSourceModel, distance)
            .join(EvidenceSourceModel, EvidenceSourceModel.id == EvidenceRecordModel.source_id)
            .where(
                EvidenceRecordModel.research_run_id == run.id,
                EvidenceRecordModel.embedding.is_not(None),
                EvidenceRecordModel.embedding_model == embedding_model,
                EvidenceRecordModel.embedding_dimensions == embedding_dimensions,
            )
            .order_by(distance)
            .limit(top_k)
        ).all()
        return [
            RetrievedEvidence(
                id=evidence.id,
                text=evidence.summary,
                title=source.title,
                provider_name=source.provider_name,
                url=source.url,
                similarity=max(0.0, min(1.0, 1.0 - float(row_distance))),
            )
            for evidence, source, row_distance in rows
        ]

    def _research_assessment(
        self,
        claim: ClaimModel,
        run_id: UUID,
        language: UserLocale,
    ) -> ConsumerAssessment:
        rows = self._session.execute(
            select(EvidenceSourceModel, EvidenceRecordModel.source_location)
            .join(EvidenceRecordModel, EvidenceRecordModel.source_id == EvidenceSourceModel.id)
            .join(
                ClaimEvidenceRecordModel,
                ClaimEvidenceRecordModel.evidence_record_id == EvidenceRecordModel.id,
            )
            .where(
                ClaimEvidenceRecordModel.claim_id == claim.id,
                EvidenceRecordModel.research_run_id == run_id,
            )
        ).all()
        sources = [
            AssessmentSourceRead(
                title=source.title,
                provider_name=source.provider_name,
                url=source.url,
                published_at=source.published_at,
                source_location=location,
            )
            for source, location in rows
        ]
        verification = (
            VerificationLevel.MULTIPLE_SOURCES
            if len(sources) >= 2
            else VerificationLevel.SINGLE_SOURCE
            if sources
            else VerificationLevel.UNVERIFIED
        )
        localized_finding, localized_limitations = _localized_claim_content(claim, language)
        return ConsumerAssessment(
            dimension=AssessmentDimension(claim.dimension),
            title=_dimension_title(AssessmentDimension(claim.dimension), language),
            status=AssessmentStatus(claim.status),
            finding=localized_finding,
            evidence_scope=EvidenceScope(claim.subject_scope),
            verification=verification,
            verification_note=_verification_note(verification, language),
            limitations=(
                localized_limitations or (None if sources else _missing_source_note(language))
            ),
            sources=sources,
        )

    def _upsert_research_claim(
        self,
        product: ProductModel,
        brand: BrandModel | None,
        assessment: object,
        now: datetime,
    ) -> ClaimModel:
        from justsupply.schemas.consumer import AiResearchAssessment

        if not isinstance(assessment, AiResearchAssessment):
            raise TypeError("Unexpected research assessment type.")
        scope = assessment.evidence_scope
        if scope == EvidenceScope.BRAND and brand is None:
            scope = EvidenceScope.PRODUCT
        claim = self._find_claim(product, brand, scope, assessment.dimension.value)
        if claim is None:
            claim = ClaimModel(
                id=uuid4(),
                subject_scope=scope.value,
                product_id=product.id if scope == EvidenceScope.PRODUCT else None,
                brand_id=brand.id if scope == EvidenceScope.BRAND and brand is not None else None,
                dimension=assessment.dimension.value,
                created_at=now,
                updated_at=now,
            )
            self._session.add(claim)
        claim.status = assessment.status.value
        claim.statement = assessment.finding
        claim.limitations = assessment.limitations
        claim.localized_content = {
            UserLocale.ENGLISH.value: {
                "finding": assessment.finding,
                "limitations": assessment.limitations,
            },
            UserLocale.PORTUGUESE_BRAZIL.value: assessment.translations.pt_br.model_dump(),
            UserLocale.SPANISH_LATAM.value: assessment.translations.es_latam.model_dump(),
        }
        claim.origin = "ai_research"
        claim.updated_at = now
        return claim

    def _upsert_catalog_claims(
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
                product,
                brand,
                assessment.evidence_scope,
                assessment.dimension.value,
            )
            if claim is not None and claim.origin == "ai_research":
                continue
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
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(claim)
            claim.status = assessment.status.value
            claim.statement = assessment.finding
            claim.limitations = assessment.limitations
            claim.localized_content = None
            claim.origin = "catalog"
            claim.updated_at = now
            if assessment.sources and assessment.status not in {
                AssessmentStatus.NOT_DISCLOSED,
                AssessmentStatus.UNKNOWN,
            }:
                self._link_catalog_evidence(claim, source, assessment.finding, now)

    def _find_claim(
        self,
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

    def _link_catalog_evidence(
        self,
        claim: ClaimModel,
        source: EvidenceSourceModel,
        summary: str,
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
                research_run_id=None,
                source_id=source.id,
                fingerprint=fingerprint,
                summary=summary,
                excerpt=None,
                source_location=None,
                observed_at=source.published_at,
                collected_at=now,
                created_at=now,
                embedding_model=None,
                embedding_dimensions=None,
                embedding=None,
            )
            self._session.add(evidence)
        self._session.flush()
        if self._session.get(ClaimEvidenceRecordModel, (claim.id, evidence.id)) is None:
            self._session.add(
                ClaimEvidenceRecordModel(
                    claim_id=claim.id,
                    evidence_record_id=evidence.id,
                    relationship="supports",
                )
            )

    def _upsert_brand(self, names: str | None, now: datetime) -> BrandModel | None:
        name = _primary_brand_name(names)
        if name is None:
            return None
        brand = self._session.scalar(
            select(BrandModel).where(BrandModel.name_key == name.casefold())
        )
        if brand is None:
            brand = BrandModel(
                id=uuid4(),
                name=name,
                name_key=name.casefold(),
                created_at=now,
                updated_at=now,
            )
            self._session.add(brand)
        else:
            brand.name = name
            brand.updated_at = now
        return brand

    def _upsert_product(
        self,
        item: CatalogProduct,
        brand: BrandModel | None,
        now: datetime,
    ) -> ProductModel:
        product = self._session.scalar(
            select(ProductModel).where(ProductModel.barcode == item.barcode)
        )
        if product is None:
            product = ProductModel(
                id=uuid4(),
                barcode=item.barcode,
                created_at=now,
                updated_at=now,
            )
            self._session.add(product)
        product.name = item.name
        product.brand_id = brand.id if brand else None
        product.image_url = item.image_url
        product.catalog_updated_at = item.last_updated_at
        product.updated_at = now
        return product

    def _upsert_catalog_source(
        self,
        item: CatalogProduct,
        now: datetime,
    ) -> EvidenceSourceModel:
        return self._upsert_source(
            provider="Open Food Facts",
            title=f"{item.name} — Open Food Facts",
            url=item.source_url,
            source_type="public_database",
            published_at=item.last_updated_at,
            now=now,
        )

    def _upsert_research_source(self, item: object, now: datetime) -> EvidenceSourceModel:
        from justsupply.domain.research import GroundedWebSource

        if not isinstance(item, GroundedWebSource):
            raise TypeError("Unexpected research source type.")
        return self._upsert_source(
            provider=item.provider_name,
            title=item.title,
            url=item.url,
            source_type="web_research",
            published_at=None,
            now=now,
        )

    def _upsert_source(
        self,
        *,
        provider: str,
        title: str,
        url: str,
        source_type: str,
        published_at: datetime | None,
        now: datetime,
    ) -> EvidenceSourceModel:
        key = _fingerprint(url)
        source = self._session.scalar(
            select(EvidenceSourceModel).where(EvidenceSourceModel.url_key == key)
        )
        if source is None:
            source = EvidenceSourceModel(
                id=uuid4(),
                url_key=key,
                created_at=now,
                updated_at=now,
            )
            self._session.add(source)
        source.provider_name = provider
        source.title = title
        source.url = url
        source.source_type = source_type
        source.published_at = published_at
        source.retrieved_at = now
        source.updated_at = now
        return source

    def _get_product(self, barcode: str) -> ProductModel:
        product = self._session.scalar(select(ProductModel).where(ProductModel.barcode == barcode))
        if product is None:
            raise ProductNotFoundError(barcode)
        return product

    def _latest_research_run(self, product_id: UUID) -> AiResearchRunModel | None:
        return self._session.scalar(
            select(AiResearchRunModel)
            .where(AiResearchRunModel.product_id == product_id)
            .order_by(AiResearchRunModel.searched_at.desc())
            .limit(1)
        )


def _primary_brand_name(names: str | None) -> str | None:
    if names is None:
        return None
    name = names.split(",", maxsplit=1)[0].strip()
    return name or None


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _localized_claim_content(
    claim: ClaimModel,
    language: UserLocale,
) -> tuple[str, str | None]:
    content = claim.localized_content or {}
    selected = content.get(language.value)
    if not isinstance(selected, dict):
        return claim.statement, claim.limitations
    finding = selected.get("finding")
    limitations = selected.get("limitations")
    return (
        finding if isinstance(finding, str) else claim.statement,
        limitations if isinstance(limitations, str) else None,
    )


def _dimension_title(dimension: AssessmentDimension, language: UserLocale) -> str:
    titles = {
        UserLocale.ENGLISH: {
            AssessmentDimension.VEGAN_COMPOSITION: "Vegan composition",
            AssessmentDimension.ENVIRONMENTAL_IMPACT: "Environmental impact",
            AssessmentDimension.WOMEN_WORKERS: "Women workers",
            AssessmentDimension.MINORITY_INCLUSION: "Minority inclusion",
        },
        UserLocale.PORTUGUESE_BRAZIL: {
            AssessmentDimension.VEGAN_COMPOSITION: "Composição vegana",
            AssessmentDimension.ENVIRONMENTAL_IMPACT: "Impacto ambiental",
            AssessmentDimension.WOMEN_WORKERS: "Mulheres no trabalho",
            AssessmentDimension.MINORITY_INCLUSION: "Inclusão de minorias",
        },
        UserLocale.SPANISH_LATAM: {
            AssessmentDimension.VEGAN_COMPOSITION: "Composición vegana",
            AssessmentDimension.ENVIRONMENTAL_IMPACT: "Impacto ambiental",
            AssessmentDimension.WOMEN_WORKERS: "Mujeres en el trabajo",
            AssessmentDimension.MINORITY_INCLUSION: "Inclusión de minorías",
        },
    }
    return titles[language][dimension]


def _verification_note(level: VerificationLevel, language: UserLocale) -> str:
    notes = {
        UserLocale.ENGLISH: {
            VerificationLevel.MULTIPLE_SOURCES: "Backed by two or more public sources.",
            VerificationLevel.SINGLE_SOURCE: (
                "Backed by one public source; corroboration is limited."
            ),
            VerificationLevel.UNVERIFIED: "No valid public source supports this finding.",
            VerificationLevel.CATALOG_DATA: "Reported by the public product catalog.",
        },
        UserLocale.PORTUGUESE_BRAZIL: {
            VerificationLevel.MULTIPLE_SOURCES: "Sustentado por duas ou mais fontes públicas.",
            VerificationLevel.SINGLE_SOURCE: (
                "Sustentado por uma fonte pública; a confirmação é limitada."
            ),
            VerificationLevel.UNVERIFIED: "Nenhuma fonte pública válida sustenta esta conclusão.",
            VerificationLevel.CATALOG_DATA: "Informado pelo catálogo público de produtos.",
        },
        UserLocale.SPANISH_LATAM: {
            VerificationLevel.MULTIPLE_SOURCES: "Respaldado por dos o más fuentes públicas.",
            VerificationLevel.SINGLE_SOURCE: (
                "Respaldado por una fuente pública; la corroboración es limitada."
            ),
            VerificationLevel.UNVERIFIED: "Ninguna fuente pública válida respalda esta conclusión.",
            VerificationLevel.CATALOG_DATA: "Informado por el catálogo público de productos.",
        },
    }
    return notes[language][level]


def _missing_source_note(language: UserLocale) -> str:
    return {
        UserLocale.ENGLISH: (
            "No public source was attached; this finding is not treated as verified."
        ),
        UserLocale.PORTUGUESE_BRAZIL: (
            "Nenhuma fonte pública foi associada; esta conclusão não é tratada como verificada."
        ),
        UserLocale.SPANISH_LATAM: (
            "No se asoció ninguna fuente pública; esta conclusión no se considera verificada."
        ),
    }[language]
