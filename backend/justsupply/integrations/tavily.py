import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse

import httpx2 as httpx

from justsupply.domain.research import GroundedWebSource, PublicWebSearchResult
from justsupply.integrations.ai import AiResearchError

_EXCLUDED_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "scribd.com",
    "tiktok.com",
    "x.com",
    "youtube.com",
)

_AUTHORITATIVE_DOMAINS = {
    "disabilityin.org": "independent_benchmark",
    "eeoc.gov": "government",
    "gender-pay-gap.service.gov.uk": "government",
    "gov.br": "government",
    "hrc.org": "independent_benchmark",
    "openfoodfacts.org": "public_database",
    "sec.gov": "government",
    "v-label.com": "certification_registry",
    "vegan.org": "certification_registry",
    "vegansociety.com": "certification_registry",
    "wgea.gov.au": "government",
}

_LOGGER = logging.getLogger(__name__)

_WOMEN_ASPECT_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "representation": {
        "en": ("women", "female", "women in leadership", "workforce composition"),
        "pt": (
            "mulheres",
            "liderança feminina",
            "representação feminina",
            "quadro de funcionárias",
        ),
        "es": (
            "mujeres",
            "liderazgo femenino",
            "representación femenina",
            "plantilla femenina",
        ),
    },
    "pay_equity": {
        "en": ("gender pay gap", "pay equity", "equal pay", "gender wage gap"),
        "pt": (
            "equidade salarial",
            "igualdade salarial",
            "diferença salarial",
            "transparência salarial",
        ),
        "es": ("brecha salarial", "equidad salarial", "igualdad salarial", "diferencia salarial"),
    },
    "opportunity": {
        "en": ("equal opportunity", "promotion", "career advancement", "women hiring"),
        "pt": (
            "igualdade de oportunidades",
            "promoção de mulheres",
            "progressão profissional",
            "contratação de mulheres",
        ),
        "es": (
            "igualdad de oportunidades",
            "promoción de mujeres",
            "progresión profesional",
            "contratación de mujeres",
        ),
    },
}


class TavilyWebSearch:
    provider_name = "Tavily Search"

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        *,
        client: Any | None = None,
    ) -> None:
        headers = (
            {"Authorization": f"Bearer {api_key}"}
            if api_key
            else {"X-Tavily-Access-Mode": "keyless"}
        )
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_seconds
        )

    def search(
        self,
        product_name: str,
        brand: str | None,
        barcode: str,
        organization_names: tuple[str, ...] = (),
        organization_jurisdiction: str | None = None,
    ) -> PublicWebSearchResult:
        sources: list[GroundedWebSource] = []
        request_ids: list[str] = []
        failures: list[AiResearchError] = []
        company_names = _unique_names((brand, *organization_names))
        for plan in _research_queries(
            product_name,
            brand,
            barcode,
            organization_names,
            organization_jurisdiction,
        ):
            try:
                payload = self._execute_search(plan)
            except AiResearchError as error:
                failures.append(error)
                continue
            request_id = payload.get("request_id")
            if isinstance(request_id, str):
                request_ids.append(request_id)
            parsed = _parse_sources(payload.get("results"), plan, company_names)
            sources.extend(parsed)
            raw_results = payload.get("results")
            _LOGGER.debug(
                "Tavily plan=%s aspect=%s returned=%s accepted=%s",
                plan.focus,
                plan.aspect,
                len(raw_results) if isinstance(raw_results, list) else 0,
                len(parsed),
            )

        sources = _deduplicate_and_number(sources)
        if not sources:
            if failures:
                raise failures[0]
            raise AiResearchError("No usable public sources were found for this product and brand.")
        return PublicWebSearchResult(
            provider_response_id=",".join(dict.fromkeys(request_ids)) or None,
            sources=sources,
        )

    def _execute_search(self, plan: SearchPlan) -> Mapping[object, object]:
        try:
            request: dict[str, object] = {
                "query": plan.query,
                "search_depth": plan.search_depth,
                "max_results": plan.max_results,
                "topic": plan.topic,
                "include_answer": False,
                "include_raw_content": "text",
                "include_published_date": True,
                "safe_search": True,
                "exclude_domains": list(_EXCLUDED_DOMAINS),
            }
            if plan.include_domains:
                request["include_domains"] = list(plan.include_domains)
            if plan.search_depth == "advanced":
                request["chunks_per_source"] = 3
            response = self._client.post(
                "/search",
                json=request,
            )
            if response.status_code == 401:
                raise AiResearchError("Tavily rejected the API key. Check TAVILY_API_KEY in .env.")
            if response.status_code in {429, 432, 433}:
                raise AiResearchError(
                    "Tavily search quota is unavailable. Check the Tavily usage dashboard."
                )
            response.raise_for_status()
            payload = cast(object, response.json())
        except AiResearchError:
            raise
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            raise AiResearchError(
                "Public-source search is temporarily unavailable. Please try again shortly."
            ) from error
        if not isinstance(payload, Mapping):
            raise AiResearchError("Tavily returned an unexpected search response.")
        return payload

    def close(self) -> None:
        self._client.close()


@dataclass(frozen=True, slots=True)
class SearchPlan:
    focus: str
    query: str
    max_results: int = 4
    include_domains: tuple[str, ...] = ()
    search_depth: str = "basic"
    topic: str = "general"
    aspect: str | None = None
    require_company_match: bool = False


def _research_queries(
    product_name: str,
    brand: str | None,
    barcode: str,
    organization_names: tuple[str, ...] = (),
    organization_jurisdiction: str | None = None,
) -> tuple[SearchPlan, ...]:
    identity = " ".join(
        part for part in (f'"{product_name}"', f'"{brand}"' if brand else "") if part
    )
    primary_company = organization_names[0] if organization_names else brand
    company = f'"{primary_company or product_name}"'
    language = _jurisdiction_language(organization_jurisdiction)
    women_plans = _women_research_plans(company, language)
    return (
        SearchPlan(
            "vegan_composition",
            f"{identity} {barcode} ingredients vegan certification Certified Vegan "
            "Vegan Trademark V-Label official product ingredientes vegano certificado",
            search_depth="advanced",
        ),
        SearchPlan(
            "vegan_composition",
            f'{identity} {barcode} "certified vegan" OR "Vegan Trademark" OR V-Label',
            max_results=5,
            include_domains=("vegan.org", "vegansociety.com", "v-label.com"),
        ),
        SearchPlan(
            "environmental_impact",
            f"{identity} {barcode} environmental impact sustainability deforestation "
            "forest footprint climate water packaging certification official report "
            "sustentabilidade desmatamento medio ambiente",
            search_depth="advanced",
        ),
        *women_plans,
        SearchPlan(
            "minority_inclusion",
            f'{company} (LGBTQ OR disability OR race OR ethnicity OR minority) '
            '(workforce OR "equality index" OR representation)',
            max_results=5,
            include_domains=("hrc.org", "disabilityin.org", "sec.gov", "eeoc.gov"),
        ),
        SearchPlan(
            "minority_inclusion",
            f'{company} (diversity OR inclusion OR "EEO-1" OR LGBTQ OR disability OR '
            'ethnicity OR diversidade OR inclusão OR discapacidad) ("annual report" OR '
            '"sustainability report" OR "ESG report" OR relatório OR informe) PDF',
            max_results=5,
            search_depth="advanced",
        ),
        SearchPlan(
            "minority_inclusion",
            f'{company} diversity inclusion race ethnicity LGBTQ disability minority workers '
            "discrimination employment news investigation reportagem diversidade inclusão "
            "noticias diversidad inclusión discapacidad",
            max_results=6,
            topic="news",
        ),
    )


def _women_research_plans(company: str, language: str) -> tuple[SearchPlan, ...]:
    official_domains = (
        "gender-pay-gap.service.gov.uk",
        "wgea.gov.au",
        "sec.gov",
        "eeoc.gov",
        "dol.gov",
        "eige.europa.eu",
        "ilo.org",
        "gov.br",
    )
    plans: list[SearchPlan] = []
    for aspect, translations in _WOMEN_ASPECT_TERMS.items():
        terms = translations.get(language) or tuple(
            term for values in translations.values() for term in values
        )
        term_query = " OR ".join(f'"{term}"' for term in terms)
        plans.append(
            SearchPlan(
                "women_workers",
                f"{company} ({term_query}) employer workforce",
                max_results=5,
                include_domains=official_domains,
                search_depth="advanced",
                aspect=aspect,
                require_company_match=True,
            )
        )
        plans.append(
            SearchPlan(
                "women_workers",
                f"{company} ({term_query})",
                max_results=5,
                search_depth="advanced",
                topic="news",
                aspect=aspect,
                require_company_match=True,
            )
        )
    report_terms = _localized_terms("representation", language)
    plans.append(
        SearchPlan(
            "women_workers",
            f'{company} ({report_terms}) ("annual report" OR "sustainability report" OR '
            '"ESG report" OR "diversity report") PDF',
            max_results=5,
            search_depth="advanced",
            aspect="representation",
            require_company_match=True,
        )
    )
    return tuple(plans)


def _localized_terms(aspect: str, language: str) -> str:
    translations = _WOMEN_ASPECT_TERMS[aspect]
    terms = translations.get(language) or tuple(
        term for values in translations.values() for term in values
    )
    return " OR ".join(f'"{term}"' for term in terms)


def _jurisdiction_language(jurisdiction: str | None) -> str:
    normalized = _normalize_text(jurisdiction or "")
    if any(country in normalized for country in ("brazil", "brasil", "portugal")):
        return "pt"
    spanish_markers = (
        "argentina",
        "bolivia",
        "chile",
        "colombia",
        "costa rica",
        "cuba",
        "ecuador",
        "el salvador",
        "guatemala",
        "honduras",
        "mexico",
        "nicaragua",
        "panama",
        "paraguay",
        "peru",
        "spain",
        "espana",
        "uruguay",
        "venezuela",
    )
    if any(country in normalized for country in spanish_markers):
        return "es"
    return "en" if normalized else "multi"


def _parse_sources(
    value: object,
    plan: SearchPlan,
    company_names: tuple[str, ...],
) -> list[GroundedWebSource]:
    if not isinstance(value, list):
        return []
    sources: list[GroundedWebSource] = []
    seen_urls: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url")
        content = item.get("content")
        raw_content = item.get("raw_content")
        if (
            not isinstance(url, str)
            or not url.startswith(("http://", "https://"))
            or not isinstance(content, str)
            or not content.strip()
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        domain = urlparse(url).netloc.removeprefix("www.")
        if any(
            domain == excluded or domain.endswith(f".{excluded}")
            for excluded in _EXCLUDED_DOMAINS
        ):
            continue
        title = item.get("title")
        title_text = title.strip() if isinstance(title, str) and title.strip() else domain
        relevance_text = " ".join(
            value
            for value in (title_text, content, raw_content if isinstance(raw_content, str) else "")
            if value
        )
        if _looks_low_quality(url, relevance_text):
            continue
        if plan.require_company_match and not _is_relevant_women_source(
            title_text,
            domain,
            relevance_text,
            company_names,
            plan.aspect,
        ):
            continue
        cited_text = content.strip()
        if isinstance(raw_content, str) and raw_content.strip():
            cited_text = f"{cited_text}\n\nExtracted page content:\n{raw_content.strip()}"
        sources.append(
            GroundedWebSource(
                number=len(sources) + 1,
                title=title_text,
                provider_name=domain,
                url=url,
                cited_text=cited_text[:4000],
                focus=plan.focus,
                source_class=_source_class(
                    domain,
                    company_names,
                    journalistic_search=plan.topic == "news",
                ),
            )
        )
    return sources


def _is_relevant_women_source(
    title: str,
    domain: str,
    text: str,
    company_names: tuple[str, ...],
    aspect: str | None,
) -> bool:
    if not company_names or aspect not in _WOMEN_ASPECT_TERMS:
        return False
    normalized_title = _normalize_text(title)
    normalized_text = _normalize_text(text)
    company_match = any(
        _company_mentioned(normalized_title, normalized_text, domain, name)
        for name in company_names
    )
    if not company_match:
        return False
    aspect_terms = {
        _normalize_text(term)
        for terms in _WOMEN_ASPECT_TERMS[aspect].values()
        for term in terms
    }
    return any(_phrase_present(normalized_text, term) for term in aspect_terms)


def _company_mentioned(title: str, text: str, domain: str, company_name: str) -> bool:
    normalized_name = _normalize_text(company_name)
    if not normalized_name:
        return False
    if _company_domain_matches(domain, company_name):
        return True
    if len(normalized_name.replace(" ", "")) <= 5 and " " not in normalized_name:
        return _phrase_present(title, normalized_name)
    return _phrase_present(text, normalized_name)


def _phrase_present(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text))


def _looks_low_quality(url: str, text: str) -> bool:
    path = urlparse(url).path.casefold()
    if path.endswith((".js", ".css", ".map")):
        return True
    normalized = text.casefold()
    code_markers = ("webpack", "function(", "node_modules/", "sourceMappingURL=")
    return sum(marker in normalized for marker in code_markers) >= 2


def _deduplicate_and_number(sources: list[GroundedWebSource]) -> list[GroundedWebSource]:
    selected: list[GroundedWebSource] = []
    by_url: dict[str, int] = {}
    for source in sources:
        existing_index = by_url.get(source.url)
        if existing_index is not None:
            existing = selected[existing_index]
            combined_focus = ", ".join(
                dict.fromkeys([*existing.focus.split(", "), source.focus])
            )
            selected[existing_index] = GroundedWebSource(
                number=existing.number,
                title=existing.title,
                provider_name=existing.provider_name,
                url=existing.url,
                cited_text=(
                    existing.cited_text
                    if len(existing.cited_text) >= len(source.cited_text)
                    else source.cited_text
                ),
                focus=combined_focus,
                source_class=existing.source_class,
            )
            continue
        by_url[source.url] = len(selected)
        selected.append(source)
    return [
        GroundedWebSource(
            number=number,
            title=source.title,
            provider_name=source.provider_name,
            url=source.url,
            cited_text=source.cited_text,
            focus=source.focus,
            source_class=source.source_class,
        )
        for number, source in enumerate(selected, start=1)
    ]


def _source_class(
    domain: str,
    company_names: tuple[str, ...],
    *,
    journalistic_search: bool = False,
) -> str:
    for authoritative_domain, source_class in _AUTHORITATIVE_DOMAINS.items():
        if domain == authoritative_domain or domain.endswith(f".{authoritative_domain}"):
            return source_class
    if domain.endswith((".gov", ".gov.uk", ".gov.au")):
        return "government"
    if company_names:
        if any(_company_domain_matches(domain, name) for name in company_names):
            return "company_primary"
    if journalistic_search:
        return "journalism"
    return "independent_or_unclassified"


def _company_domain_matches(domain: str, company_name: str) -> bool:
    labels = [_normalize_identifier(label) for label in domain.split(".") if label]
    company_tokens = _company_tokens(company_name)
    return any(len(label) >= 4 and label in company_tokens for label in labels)


def _company_tokens(company_name: str) -> set[str]:
    legal_suffixes = {
        "company",
        "corp",
        "corporation",
        "group",
        "holding",
        "holdings",
        "inc",
        "limited",
        "ltd",
        "sa",
        "spa",
    }
    words = [
        _normalize_identifier(word)
        for word in company_name.replace("&", " ").replace("-", " ").split()
        if _normalize_identifier(word)
    ]
    meaningful = [word for word in words if word not in legal_suffixes]
    tokens = {_normalize_identifier(company_name)}
    if meaningful:
        tokens.add("".join(meaningful))
        tokens.update(word for word in meaningful if len(word) >= 4)
    return tokens


def _unique_names(values: tuple[str | None, ...]) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        name = value.strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return tuple(names)


def _normalize_identifier(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character) and character.isalnum()
    )


def _normalize_text(value: str) -> str:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return " ".join(normalized.split())
