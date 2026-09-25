# The localized copy is intentionally kept beside the business rules it explains.
# ruff: noqa: E501

import re

from justsupply.integrations.ai import AiResearcher, EmbeddingProvider
from justsupply.integrations.langchain_rag import LangChainConsumerRag
from justsupply.integrations.open_food_facts import CatalogProduct, ProductCatalog
from justsupply.repositories.consumer_evidence import SqlAlchemyConsumerEvidenceRepository
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
    ConsumerAnswerResponse,
    ConsumerAssessment,
    ConsumerCitation,
    ConsumerProductRead,
    ConsumerSearchResponse,
    EvidenceScope,
    ProductResearchResponse,
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
    ) -> None:
        self._catalog = catalog
        self._repository = repository

    def search(
        self,
        query: str,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ConsumerSearchResponse:
        normalized_query = query.strip()
        catalog_products = self._catalog.search(normalized_query)
        products = [self.assess(product, language) for product in catalog_products]
        self._repository.save_many(list(zip(catalog_products, products, strict=True)))
        products = [self.apply_research(product, language) for product in products]
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
        research = self._repository.get_research(product.barcode, language)
        if research is None:
            return product
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
            }
        )


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
    ) -> None:
        self._catalog = catalog
        self._repository = repository
        self._researcher = researcher
        self._embedding_provider = embedding_provider
        self._rag = rag
        self._ttl_days = ttl_days

    def research(
        self,
        barcode: str,
        *,
        refresh: bool,
        language: UserLocale = UserLocale.ENGLISH,
    ) -> ProductResearchResponse:
        products = self._catalog.search(barcode)
        if not products:
            raise ConsumerProductNotFoundError(barcode)
        catalog_product = products[0]
        consumer = ConsumerService(self._catalog, self._repository)
        base_product = consumer.assess(catalog_product, language)
        self._repository.save_many([(catalog_product, base_product)])
        cached = self._repository.get_research(barcode, language)
        if cached is not None and cached.fresh and not refresh:
            return ProductResearchResponse(
                product=consumer.apply_research(base_product, language), cached=True
            )

        result = self._researcher.research(
            catalog_product.name,
            catalog_product.brand,
            catalog_product.barcode,
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
            return self._insufficient_answer(question, language)
        valid_numbers = list(
            dict.fromkeys(
                number
                for number in generated.cited_evidence_numbers
                if 1 <= number <= len(evidence)
            )
        )
        if not valid_numbers:
            return self._insufficient_answer(question, language)
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
        return ConsumerAnswerResponse(
            question=question,
            answer=answer,
            insufficient_evidence=False,
            citations=citations,
            retrieval_model=self._embedding_provider.model_name,
            generation_model=self._rag.generation_model,
            prompt_version=self._rag.prompt_version,
        )

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
    if "en:vegan" in tags:
        status = AssessmentStatus.SUPPORTED
        finding_key = "vegan_supported"
    elif "en:non-vegan" in tags:
        status = AssessmentStatus.CONCERN
        finding_key = "vegan_concern"
    else:
        status = AssessmentStatus.UNKNOWN
        finding_key = "vegan_unknown"
    return _catalog_assessment(
        product,
        AssessmentDimension.VEGAN_COMPOSITION,
        _dimension_title(AssessmentDimension.VEGAN_COMPOSITION, language),
        status,
        _catalog_text(finding_key, language),
        "Ingredient analysis",
        language,
    )


def _environmental_assessment(
    product: CatalogProduct,
    language: UserLocale,
) -> ConsumerAssessment:
    grade = (product.environmental_score_grade or "").lower()
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
    return _catalog_assessment(
        product,
        AssessmentDimension.ENVIRONMENTAL_IMPACT,
        _dimension_title(AssessmentDimension.ENVIRONMENTAL_IMPACT, language),
        status,
        finding,
        "Green-Score",
        language,
    )


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
            "vegan_unknown": "There is not enough ingredient data to determine whether this product is vegan.",
            "environment_supported": "Open Food Facts reports a favorable Green-Score grade ({grade}).",
            "environment_mixed": "Open Food Facts reports a middle Green-Score grade (C).",
            "environment_concern": "Open Food Facts reports a low Green-Score grade ({grade}).",
            "environment_unknown": "No usable Green-Score is available for this product.",
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
            "vegan_unknown": "Não há dados de ingredientes suficientes para determinar se este produto é vegano.",
            "environment_supported": "O Open Food Facts informa um Green-Score favorável ({grade}).",
            "environment_mixed": "O Open Food Facts informa um Green-Score intermediário (C).",
            "environment_concern": "O Open Food Facts informa um Green-Score baixo ({grade}).",
            "environment_unknown": "Não há um Green-Score utilizável para este produto.",
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
            "vegan_unknown": "No hay suficientes datos de ingredientes para determinar si este producto es vegano.",
            "environment_supported": "Open Food Facts informa un Green-Score favorable ({grade}).",
            "environment_mixed": "Open Food Facts informa un Green-Score intermedio (C).",
            "environment_concern": "Open Food Facts informa un Green-Score bajo ({grade}).",
            "environment_unknown": "No hay un Green-Score utilizable para este producto.",
            "catalog_verification": "Informado por el catálogo comunitario Open Food Facts; revisa la página del producto y la imagen de la etiqueta antes de confiar en el dato.",
            "catalog_limitations": "Los datos del catálogo pueden estar incompletos, desactualizados o haber sido ingresados por colaboradores.",
            "women_not_researched": "La investigación sobre empleo de mujeres en la marca aún no se ejecutó para este producto.",
            "minority_not_researched": "La investigación sobre inclusión en la marca aún no se ejecutó para este producto.",
            "unverified_note": "No se completó una investigación en fuentes públicas para esta dimensión.",
            "run_research": "Ejecuta la investigación asistida por IA para buscar evidencia pública citada.",
        },
    }
    return texts[language][key]
