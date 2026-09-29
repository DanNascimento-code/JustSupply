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
        "women_workers",
        "minority_inclusion",
    }
    assert len(client.requests) == 6
    assert client.requests[2]["json"]["include_domains"] == [
        "gender-pay-gap.service.gov.uk",
        "wgea.gov.au",
        "sec.gov",
        "gov.br",
    ]
    assert client.requests[0]["path"] == "/search"
    assert client.requests[0]["json"]["include_answer"] is False
    assert client.requests[3]["json"]["search_depth"] == "advanced"
    assert client.requests[3]["json"]["chunks_per_source"] == 3
    assert '"Example Holdings"' in str(client.requests[3]["json"]["query"])


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
