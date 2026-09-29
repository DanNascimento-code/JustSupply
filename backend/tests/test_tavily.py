from typing import Any

from justsupply.integrations.ai import AiResearchError
from justsupply.integrations.tavily import TavilyWebSearch


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def post(self, path: str, *, json: dict[str, object]) -> FakeResponse:
        self.requests.append({"path": path, "json": json})
        return self.response

    def close(self) -> None:
        pass


def test_tavily_search_returns_citable_sources() -> None:
    client = FakeClient(
        FakeResponse(
            200,
            {
                "request_id": "search-1",
                "results": [
                    {
                        "title": "Example sustainability report",
                        "url": "https://www.example.org/report",
                        "content": "The report describes packaging and workforce programs.",
                        "raw_content": "The full page includes measured workforce data.",
                    },
                    {
                        "title": "Duplicate",
                        "url": "https://www.example.org/report",
                        "content": "Duplicate content.",
                    },
                    {
                        "title": "Employer gender data",
                        "url": "https://www.wgea.gov.au/data/example",
                        "content": "The public employer record reports workforce composition.",
                    },
                    {
                        "title": "Social post",
                        "url": "https://www.instagram.com/example",
                        "content": "An uncitable social post.",
                    },
                ],
            },
        )
    )
    search = TavilyWebSearch("unused", "https://api.tavily.com", 10, client=client)

    result = search.search(
        "Example product",
        "Example brand",
        "7891000100103",
        ("Example Holdings",),
    )

    assert result.provider_response_id == "search-1"
    assert len(result.sources) == 2
    assert result.sources[0].provider_name == "example.org"
    assert result.sources[0].source_class == "company_primary"
    assert result.sources[1].source_class == "government"
    assert set(result.sources[0].focus.split(", ")) == {
        "vegan_composition",
        "environmental_impact",
        "minority_inclusion",
    }
    assert len(client.requests) == 13
    assert client.requests[1]["json"]["include_domains"] == [
        "vegan.org",
        "vegansociety.com",
        "v-label.com",
    ]
    assert client.requests[3]["json"]["include_domains"] == [
        "gender-pay-gap.service.gov.uk",
        "wgea.gov.au",
        "sec.gov",
        "eeoc.gov",
        "dol.gov",
        "eige.europa.eu",
        "ilo.org",
        "gov.br",
    ]
    assert client.requests[0]["path"] == "/search"
    assert client.requests[0]["json"]["include_answer"] is False
    assert client.requests[0]["json"]["include_raw_content"] == "text"
    assert "measured workforce data" in result.sources[0].cited_text
    assert client.requests[0]["json"]["search_depth"] == "advanced"
    assert client.requests[5]["json"]["search_depth"] == "advanced"
    assert client.requests[5]["json"]["chunks_per_source"] == 3
    assert '"Example Holdings"' in str(client.requests[5]["json"]["query"])
    assert '"pay equity"' in str(client.requests[5]["json"]["query"])
    assert '"equal opportunity"' in str(client.requests[7]["json"]["query"])
    assert client.requests[4]["json"]["topic"] == "news"
    assert client.requests[6]["json"]["topic"] == "news"
    assert client.requests[8]["json"]["topic"] == "news"
    assert client.requests[12]["json"]["topic"] == "news"


def test_tavily_search_reports_quota_failure() -> None:
    client = FakeClient(FakeResponse(429, {"detail": "quota"}))
    search = TavilyWebSearch("unused", "https://api.tavily.com", 10, client=client)

    try:
        search.search("Example product", "Example brand", "7891000100103")
    except AiResearchError as error:
        assert "quota" in str(error).lower()
    else:
        raise AssertionError("Expected Tavily quota failure.")


def test_tavily_classifies_accented_company_domain_as_primary() -> None:
    client = FakeClient(
        FakeResponse(
            200,
            {
                "results": [
                    {
                        "title": "Nestlé report",
                        "url": "https://www.nestle.com/sustainability/report",
                        "content": "Nestlé reports workforce indicators.",
                    }
                ]
            },
        )
    )
    search = TavilyWebSearch("unused", "https://api.tavily.com", 10, client=client)

    result = search.search("Nescafé Classic", "Nescafé", "12345678", ("Nestlé",))

    assert result.sources[0].source_class == "company_primary"


def test_tavily_does_not_treat_similar_company_domain_as_primary() -> None:
    client = FakeClient(
        FakeResponse(
            200,
            {
                "results": [
                    {
                        "title": "Unrelated Ferrero Automotive",
                        "url": "https://www.ferrero-automotive.com/report",
                        "content": "Automotive company workforce indicators.",
                    }
                ]
            },
        )
    )
    search = TavilyWebSearch("unused", "https://api.tavily.com", 10, client=client)

    result = search.search("Nutella", "Ferrero", "3017620422003", ("Ferrero Group",))

    assert result.sources[0].source_class == "independent_or_unclassified"


def test_tavily_rejects_irrelevant_women_sources_and_code_assets() -> None:
    client = FakeClient(
        FakeResponse(
            200,
            {
                "results": [
                    {
                        "title": "Example Group publishes pay equity results",
                        "url": "https://news.example.com/example-pay-equity",
                        "content": "Example Group reported a gender pay gap measure.",
                    },
                    {
                        "title": "Unrelated workforce study",
                        "url": "https://unrelated.org/workforce",
                        "content": "A general study discusses women in leadership.",
                    },
                    {
                        "title": "Application bundle",
                        "url": "https://example.com/assets/app.js",
                        "content": "Example Group women webpack function(",
                        "raw_content": "node_modules/ sourceMappingURL=app.js.map",
                    },
                ]
            },
        )
    )
    search = TavilyWebSearch("unused", "https://api.tavily.com", 10, client=client)

    result = search.search("Product", "Example", "12345678", ("Example Group",))

    women_urls = {
        source.url
        for source in result.sources
        if "women_workers" in source.focus.split(", ")
    }
    assert "https://news.example.com/example-pay-equity" in women_urls
    assert "https://unrelated.org/workforce" not in women_urls
    assert all(not source.url.endswith(".js") for source in result.sources)


def test_tavily_uses_jurisdiction_language_for_women_queries() -> None:
    client = FakeClient(
        FakeResponse(
            200,
            {
                "results": [
                    {
                        "title": "Empresa Exemplo e igualdade salarial",
                        "url": "https://empresaexemplo.com.br/relatorio",
                        "content": "A Empresa Exemplo publicou dados de igualdade salarial.",
                    }
                ]
            },
        )
    )
    search = TavilyWebSearch("unused", "https://api.tavily.com", 10, client=client)

    search.search(
        "Produto",
        "Exemplo",
        "12345678",
        ("Empresa Exemplo",),
        "Brazil",
    )

    assert '"igualdade salarial"' in str(client.requests[5]["json"]["query"])
    assert '"equal pay"' not in str(client.requests[5]["json"]["query"])
