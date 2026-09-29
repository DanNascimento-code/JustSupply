from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from justsupply.database.models import (
    AiResearchRunModel,
    BrandModel,
    CatalogSearchCacheModel,
    ClaimEvidenceRecordModel,
    ClaimModel,
    CommunityReportAssessmentModel,
    CommunityReportAttachmentModel,
    CommunityReportModel,
    CommunityReportSourceModel,
    ConsumerAnswerCacheModel,
    EvidenceRecordModel,
    EvidenceSourceModel,
    ProductLabelImageModel,
    ProductModel,
)
from justsupply.domain.research import AiResearchResult, RetrievedEvidence
from justsupply.integrations.open_food_facts import CatalogAttribute, CatalogProduct
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    CommunityReportAssessment,
    CommunityReportCreate,
    CommunityReportOutcome,
    CommunityReportOutcomeCounts,
    CommunityReportSummary,
    ConsumerAnswerResponse,
    ConsumerAssessment,
    ConsumerProductRead,
    EvidenceScope,
    FoodCategory,
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


@dataclass(frozen=True)
class StoredLabelImage:
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class StoredCommunityReport:
    id: UUID
    submitted_at: datetime
    document_count: int


@dataclass(frozen=True)
class CommunityReportDocumentInput:
    file_name: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class StoredCommunityAttachment:
    id: UUID
    file_name: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class StoredPublicCommunityReport:
    id: UUID
    product_name: str | None
    barcode: str | None
    category: FoodCategory
    assessments: tuple[CommunityReportAssessment, ...]
    observations: str
    evidence_urls: tuple[str, ...]
    has_photo: bool
    documents: tuple[StoredCommunityAttachment, ...]
    published_at: datetime


@dataclass(frozen=True)
class StoredCommunitySearchProduct:
    report_id: UUID
    product_name: str
    barcode: str | None
    category: FoodCategory
    has_photo: bool
    published_at: datetime
    summary: CommunityReportSummary


class SqlAlchemyConsumerEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_catalog_search(self, query: str) -> list[CatalogProduct] | None:
        cache = self._session.get(CatalogSearchCacheModel, _query_key(query))
        if cache is None or cache.expires_at <= datetime.now(UTC):
            return None
        try:
            return [_catalog_product_from_json(item) for item in cache.products]
        except (KeyError, TypeError, ValueError):
            return None

    def save_catalog_search(
        self,
        query: str,
        products: Sequence[CatalogProduct],
        *,
        ttl_hours: int,
    ) -> None:
        now = datetime.now(UTC)
        key = _query_key(query)
        cache = self._session.get(CatalogSearchCacheModel, key)
        if cache is None:
            cache = CatalogSearchCacheModel(
                query_key=key,
                created_at=now,
            )
            self._session.add(cache)
        cache.query_text = query.strip()
        cache.query_type = "barcode" if query.strip().isdigit() else "text"
        cache.products = [_catalog_product_to_json(product) for product in products]
        cache.expires_at = now + timedelta(hours=ttl_hours)
        cache.updated_at = now
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError(
                "The catalog search cache could not be saved."
            ) from error

    def save_label_image(
        self,
        barcode: str,
        image_id: UUID,
        data: bytes,
        mime_type: str,
    ) -> UUID:
        product = self._get_product(barcode)
        digest = _fingerprint_bytes(data)
        existing = self._session.scalar(
            select(ProductLabelImageModel).where(
                ProductLabelImageModel.product_id == product.id,
                ProductLabelImageModel.sha256 == digest,
            )
        )
        if existing is not None:
            return existing.id
        self._session.add(
            ProductLabelImageModel(
                id=image_id,
                product_id=product.id,
                sha256=digest,
                mime_type=mime_type,
                image_data=data,
                created_at=datetime.now(UTC),
            )
        )
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError("The label image could not be saved.") from error
        return image_id

    def get_label_image(self, image_id: UUID) -> StoredLabelImage | None:
        image = self._session.get(ProductLabelImageModel, image_id)
        if image is None:
            return None
        return StoredLabelImage(data=image.image_data, mime_type=image.mime_type)

    def save_community_report(
        self,
        report: CommunityReportCreate,
        *,
        photo_data: bytes | None,
        photo_mime_type: str | None,
        documents: Sequence[CommunityReportDocumentInput] = (),
    ) -> StoredCommunityReport:
        now = datetime.now(UTC)
        product = (
            self._session.scalar(
                select(ProductModel).where(ProductModel.barcode == report.barcode)
            )
            if report.barcode is not None
            else None
        )
        report_id = uuid4()
        model = CommunityReportModel(
            id=report_id,
            product_id=product.id if product is not None else None,
            product_name=report.product_name,
            product_name_key=(
                _name_key(report.product_name) if report.product_name is not None else None
            ),
            barcode=report.barcode,
            category=report.category.value,
            details=report.details,
            photo_mime_type=photo_mime_type,
            photo_data=photo_data,
            status="published_unverified",
            created_at=now,
            reviewed_at=None,
        )
        self._session.add(model)
        try:
            self._session.flush()
            self._session.add_all(
                CommunityReportAssessmentModel(
                    report_id=report_id,
                    dimension=assessment.dimension.value,
                    outcome=assessment.outcome.value,
                )
                for assessment in report.assessments
            )
            self._session.add_all(
                CommunityReportSourceModel(
                    report_id=report_id,
                    url=url,
                    created_at=now,
                )
                for url in dict.fromkeys(str(item) for item in report.evidence_urls)
            )
            self._session.add_all(
                CommunityReportAttachmentModel(
                    id=uuid4(),
                    report_id=report_id,
                    file_name=document.file_name,
                    mime_type=document.mime_type,
                    sha256=_fingerprint_bytes(document.data),
                    file_data=document.data,
                    created_at=now,
                )
                for document in documents
            )
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError("The community report could not be saved.") from error
        return StoredCommunityReport(
            id=report_id,
            submitted_at=now,
            document_count=len(documents),
        )

    def list_public_community_reports(
        self,
        *,
        barcode: str | None = None,
        product_name: str | None = None,
        category: FoodCategory | None = None,
        limit: int = 50,
    ) -> list[StoredPublicCommunityReport]:
        statement = select(CommunityReportModel).where(
            CommunityReportModel.status == "published_unverified"
        )
        identity_filters = []
        if barcode is not None:
            identity_filters.append(CommunityReportModel.barcode == barcode)
        if product_name is not None:
            identity_filters.append(
                CommunityReportModel.product_name_key == _name_key(product_name)
            )
        if category is not None:
            statement = statement.where(CommunityReportModel.category == category.value)
        if identity_filters:
            statement = statement.where(or_(*identity_filters))
        reports = list(
            self._session.scalars(
                statement.order_by(CommunityReportModel.created_at.desc()).limit(limit)
            ).all()
        )
        if not reports:
            return []
        report_ids = [report.id for report in reports]
        assessments_by_report: dict[UUID, list[CommunityReportAssessment]] = {
            report_id: [] for report_id in report_ids
        }
        for report_id, dimension, outcome in self._session.execute(
            select(
                CommunityReportAssessmentModel.report_id,
                CommunityReportAssessmentModel.dimension,
                CommunityReportAssessmentModel.outcome,
            ).where(CommunityReportAssessmentModel.report_id.in_(report_ids))
        ).all():
            if (
                dimension in {item.value for item in AssessmentDimension}
                and outcome in {item.value for item in CommunityReportOutcome}
            ):
                assessments_by_report[report_id].append(
                    CommunityReportAssessment(
                        dimension=AssessmentDimension(dimension),
                        outcome=CommunityReportOutcome(outcome),
                    )
                )
        documents_by_report: dict[UUID, list[StoredCommunityAttachment]] = {
            report_id: [] for report_id in report_ids
        }
        for attachment in self._session.scalars(
            select(CommunityReportAttachmentModel).where(
                CommunityReportAttachmentModel.report_id.in_(report_ids)
            )
        ).all():
            documents_by_report[attachment.report_id].append(
                StoredCommunityAttachment(
                    id=attachment.id,
                    file_name=attachment.file_name,
                    mime_type=attachment.mime_type,
                    data=attachment.file_data,
                )
            )
        sources_by_report: dict[UUID, list[str]] = {report_id: [] for report_id in report_ids}
        for report_id, url in self._session.execute(
            select(CommunityReportSourceModel.report_id, CommunityReportSourceModel.url)
            .where(CommunityReportSourceModel.report_id.in_(report_ids))
            .order_by(
                CommunityReportSourceModel.created_at,
                CommunityReportSourceModel.url,
            )
        ).all():
            sources_by_report[report_id].append(url)
        return [
            StoredPublicCommunityReport(
                id=report.id,
                product_name=report.product_name,
                barcode=report.barcode,
                category=FoodCategory(report.category),
                assessments=tuple(assessments_by_report[report.id]),
                observations=report.details,
                evidence_urls=tuple(sources_by_report[report.id]),
                has_photo=report.photo_data is not None,
                documents=tuple(documents_by_report[report.id]),
                published_at=report.created_at,
            )
            for report in reports
        ]

    def search_community_products(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[StoredCommunitySearchProduct]:
        normalized_query = query.strip()
        name_query = _name_key(normalized_query)
        filters = [CommunityReportModel.product_name_key.contains(name_query)]
        if normalized_query.isdigit():
            filters.append(CommunityReportModel.barcode == normalized_query)
        reports = list(
            self._session.scalars(
                select(CommunityReportModel)
                .where(
                    CommunityReportModel.status == "published_unverified",
                    or_(*filters),
                )
                .order_by(CommunityReportModel.created_at.desc())
                .limit(200)
            ).all()
        )
        results: list[StoredCommunitySearchProduct] = []
        seen: set[tuple[str | None, str | None]] = set()
        for report in reports:
            key = (report.barcode, report.product_name_key)
            if key in seen:
                continue
            seen.add(key)
            product_name = report.product_name or f"Product {report.barcode}"
            results.append(
                StoredCommunitySearchProduct(
                    report_id=report.id,
                    product_name=product_name,
                    barcode=report.barcode,
                    category=FoodCategory(report.category),
                    has_photo=report.photo_data is not None,
                    published_at=report.created_at,
                    summary=self.get_community_report_summary(
                        report.barcode,
                        product_name,
                    ),
                )
            )
            if len(results) >= limit:
                break
        return results

    def get_public_community_report_photo(
        self,
        report_id: UUID,
    ) -> StoredLabelImage | None:
        report = self._session.get(CommunityReportModel, report_id)
        if (
            report is None
            or report.status != "published_unverified"
            or report.photo_data is None
            or report.photo_mime_type is None
        ):
            return None
        return StoredLabelImage(data=report.photo_data, mime_type=report.photo_mime_type)

    def get_public_community_report_document(
        self,
        report_id: UUID,
        attachment_id: UUID,
    ) -> StoredCommunityAttachment | None:
        attachment = self._session.scalar(
            select(CommunityReportAttachmentModel)
            .join(
                CommunityReportModel,
                CommunityReportModel.id == CommunityReportAttachmentModel.report_id,
            )
            .where(
                CommunityReportAttachmentModel.id == attachment_id,
                CommunityReportAttachmentModel.report_id == report_id,
                CommunityReportModel.status == "published_unverified",
            )
        )
        if attachment is None:
            return None
        return StoredCommunityAttachment(
            id=attachment.id,
            file_name=attachment.file_name,
            mime_type=attachment.mime_type,
            data=attachment.file_data,
        )

    def get_community_report_summary(
        self,
        barcode: str | None,
        product_name: str,
    ) -> CommunityReportSummary:
        identity_filters = [
            CommunityReportModel.product_name_key == _name_key(product_name)
        ]
        if barcode is not None:
            identity_filters.append(CommunityReportModel.barcode == barcode)
        identity = or_(*identity_filters)
        active = CommunityReportModel.status.in_(
            ("pending_review", "published_unverified")
        )
        total = self._session.scalar(
            select(func.count(CommunityReportModel.id)).where(identity, active)
        ) or 0
        pending = self._session.scalar(
            select(func.count(CommunityReportModel.id)).where(
                identity,
                CommunityReportModel.status == "pending_review",
            )
        ) or 0
        rows = self._session.execute(
            select(
                CommunityReportAssessmentModel.dimension,
                CommunityReportAssessmentModel.outcome,
                func.count(CommunityReportAssessmentModel.report_id),
            )
            .join(
                CommunityReportModel,
                CommunityReportModel.id == CommunityReportAssessmentModel.report_id,
            )
            .where(identity, active)
            .group_by(
                CommunityReportAssessmentModel.dimension,
                CommunityReportAssessmentModel.outcome,
            )
        ).all()
        counts: dict[AssessmentDimension, CommunityReportOutcomeCounts] = {}
        for dimension, outcome, count in rows:
            if (
                dimension not in {item.value for item in AssessmentDimension}
                or outcome not in {item.value for item in CommunityReportOutcome}
            ):
                continue
            assessment_dimension = AssessmentDimension(dimension)
            current = counts.setdefault(
                assessment_dimension,
                CommunityReportOutcomeCounts(),
            )
            counts[assessment_dimension] = current.model_copy(update={outcome: count})
        return CommunityReportSummary(
            total=total,
            pending_review=pending,
            assessment_counts=counts,
        )

    def get_cached_answer(
        self,
        barcode: str,
        question: str,
        *,
        top_k: int,
        language: UserLocale,
    ) -> ConsumerAnswerResponse | None:
        product = self._get_product(barcode)
        run = self._latest_research_run(product.id)
        if run is None:
            return None
        cache = self._session.scalar(
            select(ConsumerAnswerCacheModel).where(
                ConsumerAnswerCacheModel.research_run_id == run.id,
                ConsumerAnswerCacheModel.question_key == _question_key(question),
                ConsumerAnswerCacheModel.language == language.value,
                ConsumerAnswerCacheModel.top_k == top_k,
            )
        )
        if cache is None:
            return None
        try:
            return ConsumerAnswerResponse.model_validate(cache.response).model_copy(
                update={"cached": True}
            )
        except ValueError:
            return None

    def save_cached_answer(
        self,
        barcode: str,
        question: str,
        response: ConsumerAnswerResponse,
        *,
        top_k: int,
        language: UserLocale,
    ) -> None:
        product = self._get_product(barcode)
        run = self._latest_research_run(product.id)
        if run is None:
            return
        key = _question_key(question)
        cache = self._session.scalar(
            select(ConsumerAnswerCacheModel).where(
                ConsumerAnswerCacheModel.research_run_id == run.id,
                ConsumerAnswerCacheModel.question_key == key,
                ConsumerAnswerCacheModel.language == language.value,
                ConsumerAnswerCacheModel.top_k == top_k,
            )
        )
        if cache is None:
            cache = ConsumerAnswerCacheModel(
                id=uuid4(),
                research_run_id=run.id,
                question_key=key,
                language=language.value,
                top_k=top_k,
                created_at=datetime.now(UTC),
            )
            self._session.add(cache)
        cache.question = question.strip()
        cache.response = response.model_copy(update={"cached": False}).model_dump(mode="json")
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise EvidencePersistenceError(
                "The grounded answer cache could not be saved."
            ) from error

    def save_many(self, products: Sequence[AssessedCatalogProduct]) -> None:
        now = datetime.now(UTC)
        try:
            for catalog_product, assessed_product in products:
                brand = self._upsert_brand(catalog_product.brand, now)
                self._session.flush()
                product = self._upsert_product(catalog_product, brand, now)
                source = self._upsert_catalog_source(catalog_product, now)
                sources_by_url = {source.url: source}
                assessment_sources: dict[AssessmentDimension, EvidenceSourceModel] = {}
                for assessment in assessed_product.assessments:
                    if not assessment.sources:
                        continue
                    assessment_source = assessment.sources[0]
                    stored_source = sources_by_url.get(assessment_source.url)
                    if stored_source is None:
                        stored_source = self._upsert_source(
                            provider=assessment_source.provider_name,
                            title=assessment_source.title,
                            url=assessment_source.url,
                            source_type="public_database",
                            published_at=assessment_source.published_at,
                            now=now,
                        )
                        sources_by_url[assessment_source.url] = stored_source
                    assessment_sources[assessment.dimension] = stored_source
                self._session.flush()
                self._upsert_catalog_claims(
                    assessed_product,
                    product,
                    brand,
                    source,
                    assessment_sources,
                    now,
                )
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
        *,
        expected_prompt_version: str | None = None,
    ) -> StoredResearch | None:
        product = self._get_product(barcode)
        product_run = self._latest_research_run(product.id)
        brand_run = (
            self._latest_brand_research_run(product.brand_id)
            if product.brand_id is not None
            else None
        )
        if product_run is None and brand_run is None:
            return None
        assessments: dict[AssessmentDimension, ConsumerAssessment] = {}
        run_ids: set[UUID] = set()
        if brand_run is not None and product.brand_id is not None:
            run_ids.add(brand_run.id)
            brand_statement = select(ClaimModel).where(
                ClaimModel.brand_id == product.brand_id,
                ClaimModel.origin == "ai_research",
            )
            if brand_run.product_id != product.id:
                brand_statement = brand_statement.where(
                    ClaimModel.dimension.in_(
                        {
                            AssessmentDimension.WOMEN_WORKERS.value,
                            AssessmentDimension.MINORITY_INCLUSION.value,
                        }
                    )
                )
            for claim in self._session.scalars(brand_statement).all():
                if claim.dimension in {item.value for item in AssessmentDimension}:
                    dimension = AssessmentDimension(claim.dimension)
                    assessments[dimension] = self._research_assessment(
                        claim, brand_run.id, language
                    )
        if product_run is not None:
            run_ids.add(product_run.id)
            product_claims = self._session.scalars(
                select(ClaimModel).where(
                    ClaimModel.product_id == product.id,
                    ClaimModel.origin == "ai_research",
                )
            ).all()
            for claim in product_claims:
                if claim.dimension in {item.value for item in AssessmentDimension}:
                    dimension = AssessmentDimension(claim.dimension)
                    assessments[dimension] = self._research_assessment(
                        claim, product_run.id, language
                    )
        selected_run = product_run or brand_run
        if selected_run is None:
            return None
        brand = self._session.get(BrandModel, product.brand_id) if product.brand_id else None
        total_sources = len(
            self._session.scalars(
                select(EvidenceRecordModel.id).where(
                    EvidenceRecordModel.research_run_id.in_(run_ids)
                )
            ).all()
        )
        return StoredResearch(
            assessments=assessments,
            metadata=ProductResearchMetadata(
                researched_at=max(
                    run.searched_at
                    for run in (product_run, brand_run)
                    if run is not None
                ),
                model_name=selected_run.model_name,
                source_count=total_sources,
                legal_entity=brand.legal_name if brand is not None else None,
                parent_company=brand.parent_company if brand is not None else None,
                jurisdiction=brand.jurisdiction if brand is not None else None,
                entity_source_url=(
                    brand.resolution_source_url if brand is not None else None
                ),
            ),
            fresh=(
                product_run is not None and product_run.expires_at > datetime.now(UTC)
                and (
                    expected_prompt_version is None
                    or product_run.prompt_version == expected_prompt_version
                )
            ),
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
                source_location=(
                    f"Public web research — {source.focus} — {source.source_class}"
                ),
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
        if brand is not None and result.organization is not None:
            organization = result.organization
            if organization.legal_name is not None:
                brand.legal_name = organization.legal_name
            if organization.parent_company is not None:
                brand.parent_company = organization.parent_company
            if organization.jurisdiction is not None:
                brand.jurisdiction = organization.jurisdiction
            first_source = next(
                (
                    result.sources[number - 1]
                    for number in organization.source_numbers
                    if 1 <= number <= len(result.sources)
                ),
                None,
            )
            if first_source is not None:
                brand.resolution_source_url = first_source.url
            brand.resolved_at = result.searched_at
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
        product_run = self._latest_research_run(product.id)
        brand_run = (
            self._latest_brand_research_run(product.brand_id)
            if product.brand_id is not None
            else None
        )
        run_ids = {
            run.id for run in (product_run, brand_run) if run is not None
        }
        if not run_ids:
            return []
        distance = EvidenceRecordModel.embedding.cosine_distance(embedding).label("distance")
        rows = self._session.execute(
            select(EvidenceRecordModel, EvidenceSourceModel, distance)
            .join(EvidenceSourceModel, EvidenceSourceModel.id == EvidenceRecordModel.source_id)
            .where(
                EvidenceRecordModel.research_run_id.in_(run_ids),
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
        assessment_sources: dict[AssessmentDimension, EvidenceSourceModel],
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
                assessment_source = assessment_sources.get(assessment.dimension, source)
                self._link_catalog_evidence(claim, assessment_source, assessment.finding, now)

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
            provider=item.source_name,
            title=f"{item.name} — {item.source_name}",
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

    def _latest_brand_research_run(self, brand_id: UUID) -> AiResearchRunModel | None:
        return self._session.scalar(
            select(AiResearchRunModel)
            .join(ProductModel, ProductModel.id == AiResearchRunModel.product_id)
            .where(ProductModel.brand_id == brand_id)
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


def _fingerprint_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _query_key(query: str) -> str:
    normalized = " ".join(query.split()).casefold()
    return _fingerprint(f"catalog-v2:{normalized}")


def _question_key(question: str) -> str:
    return _fingerprint(" ".join(question.split()).casefold())


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _catalog_product_to_json(product: CatalogProduct) -> dict[str, object]:
    return {
        "barcode": product.barcode,
        "name": product.name,
        "brand": product.brand,
        "image_url": product.image_url,
        "ingredients_analysis_tags": sorted(product.ingredients_analysis_tags),
        "environmental_score_grade": product.environmental_score_grade,
        "last_updated_at": (
            product.last_updated_at.isoformat() if product.last_updated_at is not None else None
        ),
        "source_url": product.source_url,
        "ingredients_text": product.ingredients_text,
        "ingredients_tags": sorted(product.ingredients_tags),
        "labels_tags": sorted(product.labels_tags),
        "non_vegan_ingredients": list(product.non_vegan_ingredients),
        "maybe_non_vegan_ingredients": list(product.maybe_non_vegan_ingredients),
        "unknown_ingredients_count": product.unknown_ingredients_count,
        "vegan_attribute": _attribute_to_json(product.vegan_attribute),
        "forest_footprint_attribute": _attribute_to_json(product.forest_footprint_attribute),
        "ingredients_image_url": product.ingredients_image_url,
        "brand_owner": product.brand_owner,
        "source_name": product.source_name,
        "ingredients_source_url": product.ingredients_source_url,
        "ingredients_source_name": product.ingredients_source_name,
        "catalog_degraded": product.catalog_degraded,
    }


def _catalog_product_from_json(payload: dict[str, object]) -> CatalogProduct:
    updated = payload.get("last_updated_at")
    return CatalogProduct(
        barcode=str(payload["barcode"]),
        name=str(payload["name"]),
        brand=_optional_string(payload.get("brand")),
        image_url=_optional_string(payload.get("image_url")),
        ingredients_analysis_tags=_string_set(payload.get("ingredients_analysis_tags")),
        environmental_score_grade=_optional_string(payload.get("environmental_score_grade")),
        last_updated_at=(datetime.fromisoformat(updated) if isinstance(updated, str) else None),
        source_url=str(payload["source_url"]),
        ingredients_text=_optional_string(payload.get("ingredients_text")),
        ingredients_tags=_string_set(payload.get("ingredients_tags")),
        labels_tags=_string_set(payload.get("labels_tags")),
        non_vegan_ingredients=_string_tuple(payload.get("non_vegan_ingredients")),
        maybe_non_vegan_ingredients=_string_tuple(payload.get("maybe_non_vegan_ingredients")),
        unknown_ingredients_count=_optional_int(payload.get("unknown_ingredients_count")),
        vegan_attribute=_attribute_from_json(payload.get("vegan_attribute")),
        forest_footprint_attribute=_attribute_from_json(
            payload.get("forest_footprint_attribute")
        ),
        ingredients_image_url=_optional_string(payload.get("ingredients_image_url")),
        brand_owner=_optional_string(payload.get("brand_owner")),
        source_name=_optional_string(payload.get("source_name")) or "Open Food Facts",
        ingredients_source_url=_optional_string(payload.get("ingredients_source_url")),
        ingredients_source_name=_optional_string(payload.get("ingredients_source_name")),
        catalog_degraded=payload.get("catalog_degraded") is True,
    )


def _attribute_to_json(attribute: CatalogAttribute | None) -> dict[str, object] | None:
    if attribute is None:
        return None
    return {"status": attribute.status, "match": attribute.match, "title": attribute.title}


def _attribute_from_json(value: object) -> CatalogAttribute | None:
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    match = value.get("match")
    title = value.get("title")
    return CatalogAttribute(
        status=status if isinstance(status, str) else None,
        match=float(match) if isinstance(match, int | float) else None,
        title=title if isinstance(title, str) else None,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _string_set(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()


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
