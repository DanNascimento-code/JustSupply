from collections.abc import Mapping
from typing import Any

import httpx2 as httpx

import justsupply.integrations.open_food_facts as open_food_facts_module
from justsupply.integrations.open_food_facts import OpenFoodFactsCatalog


class FakeResponse:
    def __init__(self, status_code: int, payload: Mapping[str, object]) -> None:
        self.status_code = status_code
        self._payload = dict(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class SequencedClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def get(self, path: str, params: dict[str, str]) -> FakeResponse:
        del path, params
        response = self.responses[self.calls]
        self.calls += 1
        return response

    def close(self) -> None:
        return None


def test_retries_once_before_falling_back_from_open_food_facts(
    monkeypatch: Any,
) -> None:
    client = SequencedClient(
        [
            FakeResponse(503, {}),
            FakeResponse(
                200,
                {
                    "product": {
                        "code": "3017620422003",
                        "product_name": "Hazelnut spread",
                        "environmental_score_grade": "d",
                    }
                },
            ),
        ]
    )
    catalog = OpenFoodFactsCatalog(
        base_url="https://world.openfoodfacts.org",
        user_agent="JustSupply tests",
        timeout_seconds=1,
    )
    catalog._client.close()  # noqa: SLF001
    catalog._client = client  # type: ignore[assignment]  # noqa: SLF001
    monkeypatch.setattr(open_food_facts_module, "sleep", lambda _: None)

    products = catalog.search("3017620422003")

    assert client.calls == 2
    assert len(products) == 1
    assert products[0].source_name == "Open Food Facts"
    assert products[0].environmental_score_grade == "d"
