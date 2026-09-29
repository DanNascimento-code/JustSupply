from collections.abc import Iterable

from justsupply.domain.research import GroundedWebSource, PublicWebSearchResult
from justsupply.integrations.ai import AiResearchError, PublicWebSearchProvider

_SOURCE_CLASS_PRIORITY = {
    "government": 6,
    "certification_registry": 5,
    "public_database": 4,
    "independent_benchmark": 3,
    "journalism": 2,
    "company_primary": 2,
    "independent_or_unclassified": 1,
    "unclassified": 0,
}


class CompositeWebSearch:
    """Merge independent retrievers while allowing either one to fail."""

    provider_name = "Composite public-web search"

    def __init__(self, providers: Iterable[PublicWebSearchProvider]) -> None:
        self._providers = tuple(providers)
        if not self._providers:
            raise ValueError("At least one public-web search provider is required.")

    def search(
        self,
        product_name: str,
        brand: str | None,
        barcode: str,
        organization_names: tuple[str, ...] = (),
        organization_jurisdiction: str | None = None,
    ) -> PublicWebSearchResult:
        sources: list[GroundedWebSource] = []
        response_ids: list[str] = []
        failures: list[AiResearchError] = []
        for provider in self._providers:
            try:
                result = provider.search(
                    product_name,
                    brand,
                    barcode,
                    organization_names,
                    organization_jurisdiction,
                )
            except AiResearchError as error:
                failures.append(error)
                continue
            sources.extend(result.sources)
            if result.provider_response_id:
                response_ids.append(f"{provider.provider_name}:{result.provider_response_id}")

        merged = _merge_sources(sources)
        if not merged:
            if failures:
                raise failures[0]
            raise AiResearchError("No usable public sources were found for this product and brand.")
        return PublicWebSearchResult(
            provider_response_id=";".join(response_ids) or None,
            sources=merged,
        )


def _merge_sources(sources: list[GroundedWebSource]) -> list[GroundedWebSource]:
    selected: list[GroundedWebSource] = []
    by_url: dict[str, int] = {}
    for source in sources:
        key = source.url.rstrip("/").casefold()
        existing_index = by_url.get(key)
        if existing_index is None:
            by_url[key] = len(selected)
            selected.append(source)
            continue
        existing = selected[existing_index]
        focuses = ", ".join(
            dict.fromkeys([*existing.focus.split(", "), *source.focus.split(", ")])
        )
        texts = [existing.cited_text]
        if source.cited_text not in existing.cited_text:
            texts.append(source.cited_text)
        stronger = max(
            (existing.source_class, source.source_class),
            key=lambda value: _SOURCE_CLASS_PRIORITY.get(value, 0),
        )
        selected[existing_index] = GroundedWebSource(
            number=existing.number,
            title=existing.title if len(existing.title) >= len(source.title) else source.title,
            provider_name=(
                existing.provider_name
                if existing.provider_name != "Google Search source"
                else source.provider_name
            ),
            url=existing.url,
            cited_text=" ".join(texts)[:4000],
            focus=focuses,
            source_class=stronger,
        )
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
