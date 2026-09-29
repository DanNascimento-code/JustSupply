from types import SimpleNamespace
from typing import Any

from justsupply.integrations.google_grounding import GoogleGroundedSearch


class FakeModels:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.models = FakeModels(responses)


def _response(
    response_id: str,
    sources: list[tuple[str, str, str]],
) -> object:
    chunks = [
        SimpleNamespace(web=SimpleNamespace(uri=url, title=title))
        for url, title, _ in sources
    ]
    supports = [
        SimpleNamespace(
            grounding_chunk_indices=[index],
            segment=SimpleNamespace(text=text),
        )
        for index, (_, _, text) in enumerate(sources)
    ]
    return SimpleNamespace(
        response_id=response_id,
        candidates=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=chunks,
                    grounding_supports=supports,
                )
            )
        ],
    )


def test_google_grounding_returns_claim_level_citations_for_each_focus() -> None:
    client = FakeClient(
        [
            _response(
                "product-search",
                [
                    (
                        "https://vegan.org/certification/example",
                        "vegan.org",
                        "The registry lists this exact product.",
                    )
                ],
            ),
            _response(
                "women-search",
                [
                    (
                        "https://gender-pay-gap.service.gov.uk/employer/example",
                        "gender-pay-gap.service.gov.uk",
                        "The employer reported its statutory gender pay gap.",
                    )
                ],
            ),
            _response(
                "inclusion-search",
                [
                    (
                        "https://www.hrc.org/resources/example",
                        "hrc.org",
                        "The company appears in the equality benchmark.",
                    )
                ],
            ),
        ]
    )
    search = GoogleGroundedSearch("unused", "gemini-search-test", 10, client=client)

    result = search.search(
        "Example product",
        "Example brand",
        "7891000100103",
        ("Example Holdings",),
    )

    assert result.provider_response_id == "product-search,women-search,inclusion-search"
    assert len(result.sources) == 3
    assert result.sources[0].source_class == "certification_registry"
    assert result.sources[1].source_class == "government"
    assert result.sources[2].source_class == "independent_benchmark"
    assert result.sources[0].focus == "vegan_composition, environmental_impact"
    assert result.sources[0].cited_text == "The registry lists this exact product."
    assert len(client.models.calls) == 3
    assert all(call["model"] == "gemini-search-test" for call in client.models.calls)
    config: Any = client.models.calls[0]["config"]
    assert config.tools[0].google_search is not None
    assert '"7891000100103"' in str(client.models.calls[0]["contents"])
    assert "Example Holdings" in str(client.models.calls[1]["contents"])


def test_google_grounding_ignores_chunks_without_claim_support() -> None:
    unsupported = SimpleNamespace(
        response_id="empty-first",
        candidates=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=[
                        SimpleNamespace(
                            web=SimpleNamespace(
                                uri="https://example.org/result",
                                title="example.org",
                            )
                        )
                    ],
                    grounding_supports=[],
                )
            )
        ],
    )
    supported = _response(
        "supported",
        [("https://wgea.gov.au/example", "wgea.gov.au", "Employer workforce data.")],
    )
    client = FakeClient([unsupported, supported, supported])
    search = GoogleGroundedSearch("unused", "gemini-search-test", 10, client=client)

    result = search.search("Example", "Brand", "12345678")

    assert len(result.sources) == 1
    assert result.sources[0].cited_text == "Employer workforce data."
    assert set(result.sources[0].focus.split(", ")) == {
        "women_workers",
        "minority_inclusion",
    }
