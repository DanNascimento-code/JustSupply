from justsupply.domain.research import GroundedWebSource, PublicWebSearchResult
from justsupply.integrations.ai import AiResearchError
from justsupply.integrations.composite_search import CompositeWebSearch


class FakeProvider:
    def __init__(
        self,
        name: str,
        result: PublicWebSearchResult | None = None,
        error: AiResearchError | None = None,
    ) -> None:
        self.provider_name = name
        self._result = result
        self._error = error

    def search(
        self,
        product_name: str,
        brand: str | None,
        barcode: str,
        organization_names: tuple[str, ...] = (),
        organization_jurisdiction: str | None = None,
    ) -> PublicWebSearchResult:
        del product_name, brand, barcode, organization_names, organization_jurisdiction
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _result(response_id: str, source: GroundedWebSource) -> PublicWebSearchResult:
    return PublicWebSearchResult(provider_response_id=response_id, sources=[source])


def test_composite_search_merges_sources_and_survives_one_provider_failure() -> None:
    source = GroundedWebSource(
        number=1,
        title="Official report",
        provider_name="example.com",
        url="https://example.com/report",
        cited_text="Reported workforce data.",
        focus="women_workers",
        source_class="company_primary",
    )
    search = CompositeWebSearch(
        [
            FakeProvider("Unavailable", error=AiResearchError("temporary")),
            FakeProvider("Available", _result("response-1", source)),
        ]
    )

    result = search.search("Product", "Brand", "12345678")

    assert result.provider_response_id == "Available:response-1"
    assert result.sources == [source]


def test_composite_search_deduplicates_and_keeps_stronger_source_class() -> None:
    google_source = GroundedWebSource(
        number=1,
        title="Report",
        provider_name="example.com",
        url="https://example.com/report",
        cited_text="Women make up part of the workforce.",
        focus="women_workers",
        source_class="independent_or_unclassified",
    )
    tavily_source = GroundedWebSource(
        number=1,
        title="Example official workforce report",
        provider_name="example.com",
        url="https://example.com/report/",
        cited_text="The company published measured workforce data.",
        focus="minority_inclusion",
        source_class="company_primary",
    )
    search = CompositeWebSearch(
        [
            FakeProvider("Google", _result("g-1", google_source)),
            FakeProvider("Tavily", _result("t-1", tavily_source)),
        ]
    )

    result = search.search("Product", "Brand", "12345678")

    assert len(result.sources) == 1
    assert result.sources[0].number == 1
    assert result.sources[0].source_class == "company_primary"
    assert set(result.sources[0].focus.split(", ")) == {
        "women_workers",
        "minority_inclusion",
    }
    assert "measured workforce data" in result.sources[0].cited_text
