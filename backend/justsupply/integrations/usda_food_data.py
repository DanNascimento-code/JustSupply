from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx2 as httpx

from justsupply.integrations.open_food_facts import CatalogProduct, CatalogUnavailableError


class UsdaFoodDataCatalog:
    """Optional fallback for branded foods missing from Open Food Facts."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        *,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self._base_url, timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def search(self, query: str) -> list[CatalogProduct]:
        try:
            response = self._client.post(
                "/foods/search",
                params={"api_key": self._api_key},
                json={
                    "query": query.strip(),
                    "dataType": ["Branded"],
                    "pageSize": 8,
                },
            )
            response.raise_for_status()
            payload = cast(object, response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise CatalogUnavailableError(
                "USDA FoodData Central is temporarily unavailable."
            ) from error
        if not isinstance(payload, Mapping):
            raise CatalogUnavailableError("USDA FoodData Central returned an unexpected response.")
        foods = payload.get("foods")
        if not isinstance(foods, list):
            return []
        products: list[CatalogProduct] = []
        for item in foods:
            if not isinstance(item, Mapping):
                continue
            product = _to_product(item, self._base_url)
            if product is not None:
                products.append(product)
        return products


def _to_product(payload: Mapping[object, object], base_url: str) -> CatalogProduct | None:
    barcode = _text(payload, "gtinUpc")
    fdc_id = payload.get("fdcId")
    name = _text(payload, "description")
    if barcode is None or not barcode.isdigit() or not 8 <= len(barcode) <= 14:
        return None
    if not isinstance(fdc_id, int) or name is None:
        return None
    return CatalogProduct(
        barcode=barcode,
        name=name.title(),
        brand=_text(payload, "brandName") or _text(payload, "brandOwner"),
        brand_owner=_text(payload, "brandOwner"),
        image_url=None,
        ingredients_analysis_tags=frozenset(),
        environmental_score_grade=None,
        last_updated_at=_date(payload, "publishedDate"),
        source_url=f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients",
        ingredients_text=_text(payload, "ingredients"),
        source_name="USDA FoodData Central",
    )


def _text(payload: Mapping[object, object], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _date(payload: Mapping[object, object], key: str) -> datetime | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
