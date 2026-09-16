from justsupply.integrations.open_food_facts import CatalogProduct, ProductCatalog
from justsupply.repositories.consumer_evidence import (
    ConsumerEvidenceRepository,
    NullConsumerEvidenceRepository,
)
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    ConsumerAssessment,
    ConsumerProductRead,
    ConsumerSearchResponse,
    EvidenceScope,
    SearchQueryType,
)

DISCLAIMER = (
    "JustSupply summarizes available evidence; it does not certify products or brands. "
    "Missing information is not evidence of harmful practice."
)


class ConsumerService:
    def __init__(
        self,
        catalog: ProductCatalog,
        evidence_repository: ConsumerEvidenceRepository | None = None,
    ) -> None:
        self._catalog = catalog
        self._evidence_repository = evidence_repository or NullConsumerEvidenceRepository()

    def search(self, query: str) -> ConsumerSearchResponse:
        normalized_query = query.strip()
        catalog_products = self._catalog.search(normalized_query)
        products = [self._assess(product) for product in catalog_products]
        self._evidence_repository.save_many(list(zip(catalog_products, products, strict=True)))
        products = [self._apply_reviewed_brand_evidence(product) for product in products]
        return ConsumerSearchResponse(
            query=normalized_query,
            query_type=(
                SearchQueryType.BARCODE
                if normalized_query.isdigit() and 8 <= len(normalized_query) <= 14
                else SearchQueryType.TEXT
            ),
            items=products,
            total=len(products),
            disclaimer=DISCLAIMER,
        )

    def _apply_reviewed_brand_evidence(
        self,
        product: ConsumerProductRead,
    ) -> ConsumerProductRead:
        reviewed_assessments = self._evidence_repository.approved_brand_assessments(product.brand)
        if not reviewed_assessments:
            return product

        assessments = [
            reviewed_assessments.get(assessment.dimension, assessment)
            for assessment in product.assessments
        ]
        return product.model_copy(
            update={
                "assessments": assessments,
                "evidence_coverage_percent": _evidence_coverage(assessments),
            }
        )

    def _assess(self, product: CatalogProduct) -> ConsumerProductRead:
        assessments = [
            _vegan_assessment(product),
            _environmental_assessment(product),
            _not_disclosed_assessment(
                AssessmentDimension.WOMEN_WORKERS,
                "Women workers",
                "This product catalog does not provide evidence about women workers, wages, "
                "leadership, or workplace protections for this brand.",
            ),
            _not_disclosed_assessment(
                AssessmentDimension.MINORITY_INCLUSION,
                "Minority inclusion",
                "This product catalog does not provide evidence about racialized, Indigenous, "
                "LGBTQIA+, disabled, migrant, or other excluded workers for this brand.",
            ),
        ]
        return ConsumerProductRead(
            barcode=product.barcode,
            name=product.name,
            brand=product.brand,
            image_url=product.image_url,
            source_url=product.source_url,
            source_name="Open Food Facts",
            last_updated_at=product.last_updated_at,
            evidence_coverage_percent=_evidence_coverage(assessments),
            assessments=assessments,
        )


def _vegan_assessment(product: CatalogProduct) -> ConsumerAssessment:
    tags = product.ingredients_analysis_tags
    if "en:vegan" in tags:
        status = AssessmentStatus.SUPPORTED
        finding = "The catalog's ingredient analysis supports a vegan formulation."
    elif "en:non-vegan" in tags:
        status = AssessmentStatus.CONCERN
        finding = "The catalog's ingredient analysis identifies non-vegan ingredients."
    else:
        status = AssessmentStatus.UNKNOWN
        finding = "There is not enough ingredient data to determine whether this product is vegan."

    return ConsumerAssessment(
        dimension=AssessmentDimension.VEGAN_COMPOSITION,
        title="Vegan composition",
        status=status,
        finding=finding,
        evidence_scope=EvidenceScope.PRODUCT,
        sources=[_catalog_source(product, "Ingredient analysis")],
    )


def _environmental_assessment(product: CatalogProduct) -> ConsumerAssessment:
    grade = (product.environmental_score_grade or "").lower()
    if grade in {"a", "b"}:
        status = AssessmentStatus.SUPPORTED
        finding = f"Open Food Facts reports a favorable Green-Score grade ({grade.upper()})."
    elif grade == "c":
        status = AssessmentStatus.MIXED
        finding = "Open Food Facts reports a middle Green-Score grade (C)."
    elif grade in {"d", "e"}:
        status = AssessmentStatus.CONCERN
        finding = f"Open Food Facts reports a low Green-Score grade ({grade.upper()})."
    else:
        status = AssessmentStatus.UNKNOWN
        finding = "No usable Green-Score is available for this product."

    return ConsumerAssessment(
        dimension=AssessmentDimension.ENVIRONMENTAL_IMPACT,
        title="Environmental impact",
        status=status,
        finding=finding,
        evidence_scope=EvidenceScope.PRODUCT,
        sources=[_catalog_source(product, "Green-Score")],
    )


def _not_disclosed_assessment(
    dimension: AssessmentDimension,
    title: str,
    finding: str,
) -> ConsumerAssessment:
    return ConsumerAssessment(
        dimension=dimension,
        title=title,
        status=AssessmentStatus.NOT_DISCLOSED,
        finding=finding,
        evidence_scope=EvidenceScope.BRAND,
    )


def _catalog_source(product: CatalogProduct, location: str) -> AssessmentSourceRead:
    return AssessmentSourceRead(
        title=f"{product.name} — Open Food Facts",
        provider_name="Open Food Facts",
        url=product.source_url,
        published_at=product.last_updated_at,
        source_location=location,
    )


def _evidence_coverage(assessments: list[ConsumerAssessment]) -> int:
    evidenced_dimensions = sum(
        assessment.status
        in {AssessmentStatus.SUPPORTED, AssessmentStatus.MIXED, AssessmentStatus.CONCERN}
        for assessment in assessments
    )
    return round(evidenced_dimensions / len(assessments) * 100)
