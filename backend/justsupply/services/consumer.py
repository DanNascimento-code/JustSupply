# The localized copy is intentionally kept beside the business rules it explains.
# ruff: noqa: E501

import re
import unicodedata
from urllib.parse import urlencode
from uuid import UUID, uuid4

from justsupply.integrations.ai import AiResearcher, EmbeddingProvider
from justsupply.integrations.langchain_rag import LangChainConsumerRag
from justsupply.integrations.open_food_facts import (
    CatalogProduct,
    CatalogUnavailableError,
    ProductCatalog,
)
from justsupply.repositories.consumer_evidence import (
    CommunityReportDocumentInput,
    SqlAlchemyConsumerEvidenceRepository,
    StoredCommunitySearchProduct,
    StoredLabelImage,
)
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    CommunityReportAttachmentRead,
    CommunityReportCreate,
    CommunityReportRead,
    CommunityReportStatus,
    ConsumerAnswerResponse,
    ConsumerAssessment,
    ConsumerCitation,
    ConsumerProductRead,
    ConsumerSearchResponse,
    EvidenceScope,
    FoodCategory,
    ProductResearchResponse,
    PublicCommunityReportList,
    PublicCommunityReportRead,
    SearchQueryType,
    UserLocale,
    VerificationLevel,
)

DISCLAIMERS = {
    UserLocale.ENGLISH: (
        "JustSupply summarizes public evidence and AI-assisted research; it does not certify "
        "products or brands. Missing information is not evidence of harmful practice. Always "
        "inspect sources."
    ),
    UserLocale.PORTUGUESE_BRAZIL: (
        "O JustSupply resume evidências públicas e pesquisas auxiliadas por IA; ele não certifica "
        "produtos nem marcas. A ausência de informação não comprova uma prática prejudicial. "
        "Sempre consulte as fontes."
    ),
    UserLocale.SPANISH_LATAM: (
        "JustSupply resume evidencia pública e investigación asistida por IA; no certifica "
        "productos ni marcas. La falta de información no demuestra una práctica perjudicial. "
        "Siempre revisa las fuentes."
    ),
}


class ConsumerProductNotFoundError(Exception):
    def __init__(self, barcode: str) -> None:
        super().__init__(f"No catalog product was found for barcode '{barcode}'.")


class ConsumerService:
    def __init__(
        self,
        catalog: ProductCatalog,
        repository: SqlAlchemyConsumerEvidenceRepository,
        *,
        catalog_cache_ttl_hours: int = 24,
    ) -> None:
        self._catalog = catalog
        self._repository = repository
        self._catalog_cache_ttl_hours = catalog_cache_ttl_hours

    def search(
        self,
        query: str,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ConsumerSearchResponse:
        normalized_query = query.strip()
        community_products = self._repository.search_community_products(normalized_query)
        catalog_products = self._repository.get_catalog_search(normalized_query)
        catalog_cache_hit = catalog_products is not None
        catalog_request_succeeded = True
        if catalog_products is None:
            try:
                catalog_products = self._catalog.search(normalized_query)
            except CatalogUnavailableError:
                if not community_products:
                    raise
                catalog_products = []
                catalog_request_succeeded = False
        products = [self.assess(product, language) for product in catalog_products]
        self._repository.save_many(list(zip(catalog_products, products, strict=True)))
        if not catalog_cache_hit and catalog_request_succeeded:
            self._repository.save_catalog_search(
                normalized_query,
                catalog_products,
                ttl_hours=self._catalog_cache_ttl_hours,
            )
        products = [self.apply_research(product, language) for product in products]
        catalog_barcodes = {product.barcode for product in products if product.barcode}
        catalog_names = {_search_key(product.name) for product in products}
        products.extend(
            self._community_search_product(product)
            for product in community_products
            if product.barcode not in catalog_barcodes
            and _search_key(product.product_name) not in catalog_names
        )
        return ConsumerSearchResponse(
            query=normalized_query,
            query_type=(
                SearchQueryType.BARCODE
                if normalized_query.isdigit() and 8 <= len(normalized_query) <= 14
                else SearchQueryType.TEXT
            ),
            items=products,
            total=len(products),
            disclaimer=DISCLAIMERS[language],
        )

    def _community_search_product(
        self,
        product: StoredCommunitySearchProduct,
    ) -> ConsumerProductRead:
        filter_params = (
            {"barcode": product.barcode}
            if product.barcode is not None
            else {"product_name": product.product_name}
        )
        return ConsumerProductRead(
            barcode=product.barcode,
            name=product.product_name,
            brand=None,
            category=product.category,
            catalog_product=False,
            image_url=(
                f"/api/v1/consumer/reports/{product.report_id}/photo"
                if product.has_photo
                else None
            ),
            source_url=f"/community-reports?{urlencode(filter_params)}",
            source_name="JustSupply community",
            last_updated_at=product.published_at,
            evidence_coverage_percent=0,
            assessments=[],
            community_reports=product.summary,
        )

    def assess(
        self,
        product: CatalogProduct,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ConsumerProductRead:
        assessments = [
            _vegan_assessment(product, language),
            _environmental_assessment(product, language),
            _unverified_assessment(
                AssessmentDimension.WOMEN_WORKERS,
                language,
            ),
            _unverified_assessment(
                AssessmentDimension.MINORITY_INCLUSION,
                language,
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

    def apply_research(
        self,
        product: ConsumerProductRead,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ConsumerProductRead:
        community_reports = self._repository.get_community_report_summary(
            product.barcode,
            product.name,
        )
        if product.barcode is None:
            return product.model_copy(update={"community_reports": community_reports})
        research = self._repository.get_research(product.barcode, language)
        if research is None:
            return product.model_copy(update={"community_reports": community_reports})
        assessments = []
        for catalog_assessment in product.assessments:
            researched = research.assessments.get(catalog_assessment.dimension)
            if researched is None:
                assessments.append(catalog_assessment)
            elif catalog_assessment.dimension in {
                AssessmentDimension.WOMEN_WORKERS,
                AssessmentDimension.MINORITY_INCLUSION,
            } or catalog_assessment.status in {
                AssessmentStatus.UNKNOWN,
                AssessmentStatus.NOT_DISCLOSED,
            }:
                assessments.append(researched)
            else:
                assessments.append(catalog_assessment)
        return product.model_copy(
            update={
                "assessments": assessments,
                "evidence_coverage_percent": _evidence_coverage(assessments),
                "research": research.metadata,
                "community_reports": community_reports,
            }
        )

    def submit_community_report(
        self,
        report: CommunityReportCreate,
        *,
        photo_data: bytes | None,
        photo_mime_type: str | None,
        documents: list[CommunityReportDocumentInput],
        language: UserLocale = UserLocale.ENGLISH,
    ) -> CommunityReportRead:
        stored = self._repository.save_community_report(
            report,
            photo_data=photo_data,
            photo_mime_type=photo_mime_type,
            documents=documents,
        )
        notice = {
            UserLocale.ENGLISH: (
                "Your report was published as unverified community content. It does not change "
                "the product's evidence assessment."
            ),
            UserLocale.PORTUGUESE_BRAZIL: (
                "Seu relato foi publicado como conteúdo comunitário não verificado. Ele não "
                "altera a avaliação de evidências do produto."
            ),
            UserLocale.SPANISH_LATAM: (
                "Tu reporte fue publicado como contenido comunitario no verificado. No cambia "
                "la evaluación de evidencia del producto."
            ),
        }[language]
        return CommunityReportRead(
            id=stored.id,
            product_name=report.product_name,
            barcode=report.barcode,
            category=report.category,
            assessments=report.assessments,
            status=CommunityReportStatus.PUBLISHED_UNVERIFIED,
            has_photo=photo_data is not None,
            document_count=stored.document_count,
            submitted_at=stored.submitted_at,
            notice=notice,
        )

    def list_public_community_reports(
        self,
        *,
        barcode: str | None,
        product_name: str | None,
        category: FoodCategory | None,
        language: UserLocale,
    ) -> PublicCommunityReportList:
        reports = self._repository.list_public_community_reports(
            barcode=barcode,
            product_name=product_name,
            category=category,
        )
        items = [
            PublicCommunityReportRead(
                id=report.id,
                product_name=report.product_name,
                barcode=report.barcode,
                category=report.category,
                assessments=list(report.assessments),
                observations=report.observations,
                evidence_url=report.evidence_url,
                photo_url=(
                    f"/api/v1/consumer/reports/{report.id}/photo"
                    if report.has_photo
                    else None
                ),
                documents=[
                    CommunityReportAttachmentRead(
                        id=document.id,
                        file_name=document.file_name,
                        mime_type=document.mime_type,
                        download_url=(
                            f"/api/v1/consumer/reports/{report.id}/documents/{document.id}"
                        ),
                    )
                    for document in report.documents
                ],
                published_at=report.published_at,
            )
            for report in reports
        ]
        disclaimer = {
            UserLocale.ENGLISH: (
                "These reports are user-submitted and unverified. Read the observations and "
                "attachments critically; they do not change JustSupply's evidence assessment."
            ),
            UserLocale.PORTUGUESE_BRAZIL: (
                "Estes relatos foram enviados por usuários e não são verificados. Analise "
                "criticamente as observações e os anexos; eles não alteram a avaliação do JustSupply."
            ),
            UserLocale.SPANISH_LATAM: (
                "Estos reportes fueron enviados por usuarios y no están verificados. Analiza "
                "críticamente las observaciones y los anexos; no cambian la evaluación de JustSupply."
            ),
        }[language]
        return PublicCommunityReportList(
            items=items,
            total=len(items),
            disclaimer=disclaimer,
        )

    def get_public_community_report_photo(self, report_id: UUID) -> StoredLabelImage | None:
        return self._repository.get_public_community_report_photo(report_id)

    def get_public_community_report_document(
        self,
        report_id: UUID,
        attachment_id: UUID,
    ) -> tuple[bytes, str, str] | None:
        document = self._repository.get_public_community_report_document(
            report_id,
            attachment_id,
        )
        if document is None:
            return None
        return document.data, document.mime_type, document.file_name


class ConsumerResearchService:
    def __init__(
        self,
        catalog: ProductCatalog,
        repository: SqlAlchemyConsumerEvidenceRepository,
        researcher: AiResearcher,
        embedding_provider: EmbeddingProvider,
        rag: LangChainConsumerRag,
        *,
        ttl_days: int,
        catalog_cache_ttl_hours: int = 24,
    ) -> None:
        self._catalog = catalog
        self._repository = repository
        self._researcher = researcher
        self._embedding_provider = embedding_provider
        self._rag = rag
        self._ttl_days = ttl_days
        self._catalog_cache_ttl_hours = catalog_cache_ttl_hours

    def research(
        self,
        barcode: str,
        *,
        refresh: bool,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ProductResearchResponse:
        products = self._repository.get_catalog_search(barcode)
        cache_hit = products is not None
        if products is None:
            products = self._catalog.search(barcode)
        if not products:
            raise ConsumerProductNotFoundError(barcode)
        catalog_product = products[0]
        consumer = ConsumerService(
            self._catalog,
            self._repository,
            catalog_cache_ttl_hours=self._catalog_cache_ttl_hours,
        )
        base_product = consumer.assess(catalog_product, language)
        self._repository.save_many([(catalog_product, base_product)])
        if not cache_hit:
            self._repository.save_catalog_search(
                barcode,
                products,
                ttl_hours=self._catalog_cache_ttl_hours,
            )
        cached = self._repository.get_research(
            barcode,
            language,
            expected_prompt_version=self._researcher.prompt_version,
        )
        if cached is not None and cached.fresh and not refresh:
            return ProductResearchResponse(
                product=consumer.apply_research(base_product, language), cached=True
            )

        result = self._researcher.research(
            catalog_product.name,
            catalog_product.brand,
            catalog_product.barcode,
            ingredients_image_url=(
                catalog_product.ingredients_image_url
                if catalog_product.ingredients_text is None
                else None
            ),
            brand_owner=catalog_product.brand_owner,
        )
        embeddings = self._embedding_provider.embed_documents(
            [f"{source.title}\n{source.cited_text}" for source in result.sources]
        )
        self._repository.save_research(
            barcode,
            result,
            model_name=self._researcher.model_name,
            prompt_version=self._researcher.prompt_version,
            embeddings=embeddings,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimensions=self._embedding_provider.dimensions,
            ttl_days=self._ttl_days,
        )
        return ProductResearchResponse(
            product=consumer.apply_research(base_product, language),
            cached=False,
        )

    def ask(
        self,
        barcode: str,
        question: str,
        *,
        top_k: int,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ConsumerAnswerResponse:
        cached = self._repository.get_cached_answer(
            barcode,
            question,
            top_k=top_k,
            language=language,
        )
        if cached is not None:
            return cached
        query_embedding = self._embedding_provider.embed_query(question)
        evidence = self._repository.search_evidence(
            barcode,
            query_embedding,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimensions=self._embedding_provider.dimensions,
            top_k=top_k,
        )
        result = self._rag.answer(question, evidence, language.value)
        generated = result.generated
        if generated.insufficient_evidence or not evidence:
            response = self._insufficient_answer(question, language)
            self._repository.save_cached_answer(
                barcode,
                question,
                response,
                top_k=top_k,
                language=language,
            )
            return response
        valid_numbers = list(
            dict.fromkeys(
                number
                for number in generated.cited_evidence_numbers
                if 1 <= number <= len(evidence)
            )
        )
        if not valid_numbers:
            response = self._insufficient_answer(question, language)
            self._repository.save_cached_answer(
                barcode,
                question,
                response,
                top_k=top_k,
                language=language,
            )
            return response
        answer = re.sub(
            r"\[(\d+)\]",
            lambda match: match.group(0) if int(match.group(1)) in set(valid_numbers) else "",
            generated.answer,
        ).strip()
        citations = [
            ConsumerCitation(
                number=number,
                evidence_id=evidence[number - 1].id,
                title=evidence[number - 1].title,
                provider_name=evidence[number - 1].provider_name,
                url=evidence[number - 1].url,
                excerpt=evidence[number - 1].text,
                similarity=round(evidence[number - 1].similarity, 4),
            )
            for number in valid_numbers
        ]
        response = ConsumerAnswerResponse(
            question=question,
            answer=answer,
            insufficient_evidence=False,
            citations=citations,
            retrieval_model=self._embedding_provider.model_name,
            generation_model=self._rag.generation_model,
            prompt_version=self._rag.prompt_version,
        )
        self._repository.save_cached_answer(
            barcode,
            question,
            response,
            top_k=top_k,
            language=language,
        )
        return response

    def research_label(
        self,
        barcode: str,
        image_data: bytes,
        mime_type: str,
        *,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ProductResearchResponse:
        products = self._repository.get_catalog_search(barcode)
        cache_hit = products is not None
        if products is None:
            products = self._catalog.search(barcode)
        if not products:
            raise ConsumerProductNotFoundError(barcode)
        catalog_product = products[0]
        consumer = ConsumerService(
            self._catalog,
            self._repository,
            catalog_cache_ttl_hours=self._catalog_cache_ttl_hours,
        )
        base_product = consumer.assess(catalog_product, language)
        self._repository.save_many([(catalog_product, base_product)])
        if not cache_hit:
            self._repository.save_catalog_search(
                barcode,
                products,
                ttl_hours=self._catalog_cache_ttl_hours,
            )
        image_id = self._repository.save_label_image(
            barcode,
            uuid4(),
            image_data,
            mime_type,
        )
        source_url = f"/api/v1/consumer/label-images/{image_id}"
        result = self._researcher.research(
            catalog_product.name,
            catalog_product.brand,
            catalog_product.barcode,
            ingredients_image_bytes=image_data,
            ingredients_image_mime_type=mime_type,
            ingredients_image_source_url=source_url,
            brand_owner=catalog_product.brand_owner,
        )
        embeddings = self._embedding_provider.embed_documents(
            [f"{source.title}\n{source.cited_text}" for source in result.sources]
        )
        self._repository.save_research(
            barcode,
            result,
            model_name=self._researcher.model_name,
            prompt_version=self._researcher.prompt_version,
            embeddings=embeddings,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimensions=self._embedding_provider.dimensions,
            ttl_days=self._ttl_days,
        )
        return ProductResearchResponse(
            product=consumer.apply_research(base_product, language),
            cached=False,
        )

    def get_label_image(self, image_id: UUID) -> StoredLabelImage | None:
        return self._repository.get_label_image(image_id)

    def _insufficient_answer(
        self,
        question: str,
        language: UserLocale,
    ) -> ConsumerAnswerResponse:
        answer = {
            UserLocale.ENGLISH: (
                "The researched public evidence is not sufficient to answer this question. "
                "Try a narrower question or refresh the product research later."
            ),
            UserLocale.PORTUGUESE_BRAZIL: (
                "As evidências públicas pesquisadas não são suficientes para responder a esta "
                "pergunta. Tente uma pergunta mais específica ou atualize a pesquisa do produto."
            ),
            UserLocale.SPANISH_LATAM: (
                "La evidencia pública investigada no es suficiente para responder esta pregunta. "
                "Prueba una pregunta más específica o actualiza la investigación del producto."
            ),
        }[language]
        return ConsumerAnswerResponse(
            question=question,
            answer=answer,
            insufficient_evidence=True,
            citations=[],
            retrieval_model=self._embedding_provider.model_name,
            generation_model=self._rag.generation_model,
            prompt_version=self._rag.prompt_version,
        )


def _vegan_assessment(
    product: CatalogProduct,
    language: UserLocale,
) -> ConsumerAssessment:
    tags = product.ingredients_analysis_tags
    explicit_vegan_label = any(
        tag in product.labels_tags
        for tag in {
            "en:vegan",
            "en:certified-vegan",
            "en:vegan-society",
            "en:v-label",
        }
    )
    animal_ingredients = _animal_ingredients(product)
    ambiguous_ingredients = _ambiguous_ingredients(product)
    attribute = product.vegan_attribute
    if "en:non-vegan" in tags or animal_ingredients or (
        attribute is not None and attribute.status == "known" and attribute.match == 0
    ):
        status = AssessmentStatus.CONCERN
        finding_key = "vegan_concern_named" if animal_ingredients else "vegan_concern"
        finding = _catalog_text(finding_key, language).format(
            ingredients=", ".join(animal_ingredients[:5])
        )
    elif "en:vegan" in tags or explicit_vegan_label or (
        attribute is not None and attribute.status == "known" and attribute.match == 100
    ):
        status = AssessmentStatus.SUPPORTED
        finding = _catalog_text("vegan_supported", language)
    elif ambiguous_ingredients:
        status = AssessmentStatus.UNKNOWN
        finding = _catalog_text("vegan_ambiguous", language).format(
            ingredients=", ".join(ambiguous_ingredients[:5])
        )
    elif product.ingredients_text:
        status = AssessmentStatus.UNKNOWN
        finding = _catalog_text("vegan_no_obvious", language)
    else:
        status = AssessmentStatus.UNKNOWN
        finding = _catalog_text("vegan_unknown", language)
    return _catalog_assessment(
        product,
        AssessmentDimension.VEGAN_COMPOSITION,
        _dimension_title(AssessmentDimension.VEGAN_COMPOSITION, language),
        status,
        finding,
        "Ingredient list, labels, and vegan analysis",
        language,
    )


def _environmental_assessment(
    product: CatalogProduct,
    language: UserLocale,
) -> ConsumerAssessment:
    grade = (product.environmental_score_grade or "").lower()
    forest = product.forest_footprint_attribute
    if grade in {"a", "b"}:
        status = AssessmentStatus.SUPPORTED
        finding = _catalog_text("environment_supported", language).format(grade=grade.upper())
    elif grade == "c":
        status = AssessmentStatus.MIXED
        finding = _catalog_text("environment_mixed", language)
    elif grade in {"d", "e"}:
        status = AssessmentStatus.CONCERN
        finding = _catalog_text("environment_concern", language).format(grade=grade.upper())
    else:
        status = AssessmentStatus.UNKNOWN
        finding = _catalog_text("environment_unknown", language)
    if forest is not None and forest.status == "known" and forest.match is not None:
        if forest.match >= 80:
            finding = f"{finding} {_catalog_text('forest_supported', language)}"
        elif forest.match <= 40:
            finding = f"{finding} {_catalog_text('forest_concern', language)}"
            status = (
                AssessmentStatus.MIXED
                if status == AssessmentStatus.SUPPORTED
                else AssessmentStatus.CONCERN
            )
    return _catalog_assessment(
        product,
        AssessmentDimension.ENVIRONMENTAL_IMPACT,
        _dimension_title(AssessmentDimension.ENVIRONMENTAL_IMPACT, language),
        status,
        finding,
        "Green-Score and Forest Footprint",
        language,
    )


def _search_key(value: str) -> str:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return " ".join(normalized.split())


_ANIMAL_INGREDIENT_PATTERNS = {
    "milk": r"\b(?:milk|leite|leche)\b",
    "whey": r"\b(?:whey|soro de leite|suero de leche)\b",
    "casein": r"\b(?:casein|caseina|caseinato)\b",
    "lactose": r"\blactos[ea]\b",
    "egg": r"\b(?:egg|eggs|ovo|ovos|huevo|huevos|albumen|albumina)\b",
    "gelatin": r"\b(?:gelatin|gelatina)\b",
    "honey": r"\b(?:honey|mel|miel)\b",
    "carmine": r"\b(?:carmine|carmim|carmin|cochineal|cochonilha|cochinilla|e120)\b",
    "shellac": r"\b(?:shellac|goma laca|e904)\b",
    "lard": r"\b(?:lard|banha|manteca de cerdo)\b",
    "tallow": r"\b(?:tallow|sebo)\b",
    "fish": r"\b(?:fish|peixe|pescado|anchovy|anchova|anchoa)\b",
    "meat": r"\b(?:meat|carne|chicken|frango|pollo|beef|bovine|bovino|pork|porco|cerdo|bacon)\b",
}

_AMBIGUOUS_INGREDIENT_PATTERNS = {
    "natural flavor": r"\b(?:natural flavo(?:u)?r|aroma natural|aromas naturais)\b",
    "glycerin": r"\b(?:glycerin|glycerine|glicerina)\b",
    "mono- and diglycerides": r"\b(?:mono\s*(?:and|e|y|-)\s*diglycerides|mono e diglicerideos)\b",
    "enzymes": r"\b(?:enzyme|enzymes|enzima|enzimas)\b",
    "vitamin D3": r"\b(?:vitamin(?:a)?\s*d3)\b",
    "stearic acid": r"\b(?:stearic acid|acido estearico)\b",
}


def _animal_ingredients(product: CatalogProduct) -> list[str]:
    if product.non_vegan_ingredients:
        return list(product.non_vegan_ingredients)
    return _matched_ingredient_terms(product.ingredients_text, _ANIMAL_INGREDIENT_PATTERNS)


def _ambiguous_ingredients(product: CatalogProduct) -> list[str]:
    structured = list(product.maybe_non_vegan_ingredients)
    detected = _matched_ingredient_terms(
        product.ingredients_text,
        _AMBIGUOUS_INGREDIENT_PATTERNS,
    )
    return list(dict.fromkeys([*structured, *detected]))


def _matched_ingredient_terms(
    ingredients_text: str | None,
    patterns: dict[str, str],
) -> list[str]:
    if not ingredients_text:
        return []
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", ingredients_text.casefold())
        if not unicodedata.combining(character)
    )
    return [name for name, pattern in patterns.items() if re.search(pattern, normalized)]


def _catalog_assessment(
    product: CatalogProduct,
    dimension: AssessmentDimension,
    title: str,
    status: AssessmentStatus,
    finding: str,
    location: str,
    language: UserLocale,
) -> ConsumerAssessment:
    return ConsumerAssessment(
        dimension=dimension,
        title=title,
        status=status,
        finding=finding,
        evidence_scope=EvidenceScope.PRODUCT,
        verification=VerificationLevel.CATALOG_DATA,
        verification_note=_catalog_text("catalog_verification", language),
        limitations=_catalog_text("catalog_limitations", language),
        sources=[
            AssessmentSourceRead(
                title=f"{product.name} — Open Food Facts",
                provider_name="Open Food Facts",
                url=product.source_url,
                published_at=product.last_updated_at,
                source_location=location,
            )
        ],
    )


def _unverified_assessment(
    dimension: AssessmentDimension,
    language: UserLocale,
) -> ConsumerAssessment:
    finding_key = (
        "women_not_researched"
        if dimension == AssessmentDimension.WOMEN_WORKERS
        else "minority_not_researched"
    )
    return ConsumerAssessment(
        dimension=dimension,
        title=_dimension_title(dimension, language),
        status=AssessmentStatus.NOT_DISCLOSED,
        finding=_catalog_text(finding_key, language),
        evidence_scope=EvidenceScope.BRAND,
        verification=VerificationLevel.UNVERIFIED,
        verification_note=_catalog_text("unverified_note", language),
        limitations=_catalog_text("run_research", language),
    )


def _evidence_coverage(assessments: list[ConsumerAssessment]) -> int:
    evidenced = sum(
        item.status
        in {AssessmentStatus.SUPPORTED, AssessmentStatus.MIXED, AssessmentStatus.CONCERN}
        and item.verification != VerificationLevel.UNVERIFIED
        for item in assessments
    )
    return round(evidenced / len(assessments) * 100)


def _dimension_title(dimension: AssessmentDimension, language: UserLocale) -> str:
    return {
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
    }[language][dimension]


def _catalog_text(key: str, language: UserLocale) -> str:
    texts = {
        UserLocale.ENGLISH: {
            "vegan_supported": "The catalog's ingredient analysis supports a vegan formulation.",
            "vegan_concern": "The catalog's ingredient analysis identifies non-vegan ingredients.",
            "vegan_concern_named": "The ingredient evidence identifies likely animal-derived content: {ingredients}.",
            "vegan_ambiguous": "No confirmed animal-derived ingredient was found, but these ingredients can have more than one origin: {ingredients}.",
            "vegan_no_obvious": "No obvious animal-derived ingredient was detected in the available list, but composition and processing are not independently verified.",
            "vegan_unknown": "There is not enough ingredient data to determine whether this product is vegan.",
            "environment_supported": "Open Food Facts reports a favorable Green-Score grade ({grade}).",
            "environment_mixed": "Open Food Facts reports a middle Green-Score grade (C).",
            "environment_concern": "Open Food Facts reports a low Green-Score grade ({grade}).",
            "environment_unknown": "No usable Green-Score is available for this product.",
            "forest_supported": "The catalog's Forest Footprint attribute is favorable.",
            "forest_concern": "The catalog's Forest Footprint attribute indicates a concern.",
            "catalog_verification": "Reported by the community-maintained Open Food Facts catalog; inspect the product page and label image before relying on it.",
            "catalog_limitations": "Catalog data may be incomplete, outdated, or entered by contributors.",
            "women_not_researched": "No brand employment research has been run for this product yet.",
            "minority_not_researched": "No inclusion research has been run for this product yet.",
            "unverified_note": "No public-source research has been completed for this dimension.",
            "run_research": "Run AI-assisted research to look for cited public evidence.",
        },
        UserLocale.PORTUGUESE_BRAZIL: {
            "vegan_supported": "A análise de ingredientes do catálogo indica uma formulação vegana.",
            "vegan_concern": "A análise do catálogo identifica ingredientes não veganos.",
            "vegan_concern_named": "As evidências dos ingredientes identificam provável conteúdo de origem animal: {ingredients}.",
            "vegan_ambiguous": "Nenhum ingrediente de origem animal foi confirmado, mas estes ingredientes podem ter mais de uma origem: {ingredients}.",
            "vegan_no_obvious": "Nenhum ingrediente obviamente animal foi detectado na lista disponível, mas a composição e o processamento não foram verificados de forma independente.",
            "vegan_unknown": "Não há dados de ingredientes suficientes para determinar se este produto é vegano.",
            "environment_supported": "O Open Food Facts informa um Green-Score favorável ({grade}).",
            "environment_mixed": "O Open Food Facts informa um Green-Score intermediário (C).",
            "environment_concern": "O Open Food Facts informa um Green-Score baixo ({grade}).",
            "environment_unknown": "Não há um Green-Score utilizável para este produto.",
            "forest_supported": "O atributo Forest Footprint do catálogo é favorável.",
            "forest_concern": "O atributo Forest Footprint do catálogo indica uma preocupação.",
            "catalog_verification": "Informado pelo catálogo comunitário Open Food Facts; confira a página do produto e a imagem do rótulo antes de confiar no dado.",
            "catalog_limitations": "Os dados do catálogo podem estar incompletos, desatualizados ou ter sido inseridos por colaboradores.",
            "women_not_researched": "A pesquisa sobre emprego de mulheres na marca ainda não foi executada para este produto.",
            "minority_not_researched": "A pesquisa sobre inclusão na marca ainda não foi executada para este produto.",
            "unverified_note": "Nenhuma pesquisa em fontes públicas foi concluída para esta dimensão.",
            "run_research": "Execute a pesquisa auxiliada por IA para procurar evidências públicas citadas.",
        },
        UserLocale.SPANISH_LATAM: {
            "vegan_supported": "El análisis de ingredientes del catálogo indica una formulación vegana.",
            "vegan_concern": "El análisis del catálogo identifica ingredientes no veganos.",
            "vegan_concern_named": "La evidencia de ingredientes identifica probable contenido de origen animal: {ingredients}.",
            "vegan_ambiguous": "No se confirmó ningún ingrediente de origen animal, pero estos ingredientes pueden tener más de un origen: {ingredients}.",
            "vegan_no_obvious": "No se detectó ningún ingrediente obviamente animal en la lista disponible, pero la composición y el procesamiento no se verificaron de forma independiente.",
            "vegan_unknown": "No hay suficientes datos de ingredientes para determinar si este producto es vegano.",
            "environment_supported": "Open Food Facts informa un Green-Score favorable ({grade}).",
            "environment_mixed": "Open Food Facts informa un Green-Score intermedio (C).",
            "environment_concern": "Open Food Facts informa un Green-Score bajo ({grade}).",
            "environment_unknown": "No hay un Green-Score utilizable para este producto.",
            "forest_supported": "El atributo Forest Footprint del catálogo es favorable.",
            "forest_concern": "El atributo Forest Footprint del catálogo indica una preocupación.",
            "catalog_verification": "Informado por el catálogo comunitario Open Food Facts; revisa la página del producto y la imagen de la etiqueta antes de confiar en el dato.",
            "catalog_limitations": "Los datos del catálogo pueden estar incompletos, desactualizados o haber sido ingresados por colaboradores.",
            "women_not_researched": "La investigación sobre empleo de mujeres en la marca aún no se ejecutó para este producto.",
            "minority_not_researched": "La investigación sobre inclusión en la marca aún no se ejecutó para este producto.",
            "unverified_note": "No se completó una investigación en fuentes públicas para esta dimensión.",
            "run_research": "Ejecuta la investigación asistida por IA para buscar evidencia pública citada.",
        },
    }
    return texts[language][key]
