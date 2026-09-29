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
    ) -> PublicWebSearchResult:
        sources: list[GroundedWebSource] = []
        request_ids: list[str] = []
        failures: list[AiResearchError] = []
        company_names = _unique_names((brand, *organization_names))
        for plan in _research_queries(product_name, brand, barcode, organization_names):
            try:
                payload = self._execute_search(plan)
            except AiResearchError as error:
                failures.append(error)
                continue
            request_id = payload.get("request_id")
            if isinstance(request_id, str):
                request_ids.append(request_id)
            sources.extend(_parse_sources(payload.get("results"), plan.focus, company_names))

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
                "topic": "general",
                "include_answer": False,
                "include_raw_content": False,
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


def _research_queries(
    product_name: str,
    brand: str | None,
    barcode: str,
    organization_names: tuple[str, ...] = (),
) -> tuple[SearchPlan, ...]:
    identity = " ".join(
        part for part in (f'"{product_name}"', f'"{brand}"' if brand else "") if part
    )
    names = _unique_names((brand, *organization_names))
    company = "(" + " OR ".join(f'"{name}"' for name in names) + ")"
    if not names:
        company = f'"{product_name}"'
    return (
        SearchPlan(
            "vegan_composition",
            f"{identity} {barcode} ingredients vegan certification Certified Vegan "
            "Vegan Trademark V-Label official product",
        ),
        SearchPlan(
            "environmental_impact",
            f"{identity} {barcode} environmental impact sustainability deforestation "
            "forest footprint climate water packaging certification official report",
        ),
        SearchPlan(
            "women_workers",
            f'{company} ("gender pay gap" OR "women in leadership" OR '
            '"female workforce" OR "workforce composition")',
            max_results=5,
            include_domains=(
                "gender-pay-gap.service.gov.uk",
                "wgea.gov.au",
                "sec.gov",
                "gov.br",
            ),
        ),
        SearchPlan(
            "women_workers",
            f'{company} (women OR gender OR female) ("annual report" OR '
            '"sustainability report" OR "ESG report" OR "diversity report") PDF',
            max_results=5,
            search_depth="advanced",
        ),
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
            'ethnicity) ("annual report" OR "sustainability report" OR "ESG report") PDF',
            max_results=5,
            search_depth="advanced",
        ),
    )


def _parse_sources(
    value: object,
    focus: str,
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
        sources.append(
            GroundedWebSource(
                number=len(sources) + 1,
                title=title.strip() if isinstance(title, str) and title.strip() else domain,
                provider_name=domain,
                url=url,
                cited_text=content.strip()[:4000],
                focus=focus,
                source_class=_source_class(domain, company_names),
            )
        )
    return sources


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


def _source_class(domain: str, company_names: tuple[str, ...]) -> str:
    for authoritative_domain, source_class in _AUTHORITATIVE_DOMAINS.items():
        if domain == authoritative_domain or domain.endswith(f".{authoritative_domain}"):
            return source_class
    if domain.endswith((".gov", ".gov.uk", ".gov.au")):
        return "government"
    if company_names:
        company_tokens = {
            _normalize_identifier(token)
            for name in company_names
            for token in name.replace("&", " ").replace("-", " ").split()
            if len(token) >= 4
        }
        compact_domain = _normalize_identifier(domain)
        if any(token in compact_domain for token in company_tokens):
            return "company_primary"
    return "independent_or_unclassified"


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
