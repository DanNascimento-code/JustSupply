from typing import Any

from justsupply.integrations.wikidata import WikidataOrganizationResolver


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, *, params: dict[str, str]) -> FakeResponse:
        self.requests.append((path, params))
        return FakeResponse(self.payloads.pop(0))

    def close(self) -> None:
        pass


def test_wikidata_resolves_brand_owner_and_manufacturer() -> None:
    client = FakeClient(
        [
            {
                "search": [
                    {"id": "Q1", "label": "Example", "description": "food brand"}
                ]
            },
            {
                "entities": {
                    "Q1": {
                        "claims": {
                            "P127": [_statement("Q2")],
                            "P176": [_statement("Q3")],
                        }
                    }
                }
            },
            {
                "entities": {
                    "Q2": {"labels": {"en": {"value": "Example Holdings"}}},
                    "Q3": {"labels": {"en": {"value": "Example Foods"}}},
                }
            },
        ]
    )
    resolver = WikidataOrganizationResolver(
        "https://www.wikidata.org",
        "JustSupply test",
        10,
        client=client,
    )

    result = resolver.resolve("Example", "Example Holdings")

    assert result.names == ("Example Holdings", "Example Foods")
    assert result.source is not None
    assert result.source.source_class == "public_database"
    assert result.source.url == "https://www.wikidata.org/wiki/Q1"
    assert client.requests[0][1]["action"] == "wbsearchentities"


def test_wikidata_uses_catalog_owner_when_brand_is_unresolved() -> None:
    client = FakeClient([{"search": []}])
    resolver = WikidataOrganizationResolver(
        "https://www.wikidata.org",
        "JustSupply test",
        10,
        client=client,
    )

    result = resolver.resolve("Unknown brand", "Known Owner, Inc.")

    assert result.names == ("Known Owner, Inc.",)
    assert result.source is None


def _statement(entity_id: str) -> dict[str, Any]:
    return {
        "mainsnak": {
            "datavalue": {
                "value": {"id": entity_id},
            }
        }
    }
