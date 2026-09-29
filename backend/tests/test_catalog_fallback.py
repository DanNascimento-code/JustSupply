from dataclasses import replace
from typing import Any

from justsupply.integrations.composite_catalog import FallbackProductCatalog
from justsupply.integrations.open_food_facts import CatalogProduct, CatalogUnavailableError
from justsupply.integrations.usda_food_data import UsdaFoodDataCatalog


def _product(*, ingredients: str | None, source_name: str = "Open Food Facts") -> CatalogProduct:
    return CatalogProduct(
        barcode="012345678905",
        name="Example Snack",
        brand="Example",
        image_url="https://images.example/snack.jpg",
        ingredients_analysis_tags=frozenset(),
        environmental_score_grade=None,
        last_updated_at=None,
        source_url="https://example.test/product",
        ingredients_text=ingredients,
        source_name=source_name,
    )


class FakeCatalog:
    def __init__(
        self,
        products: list[CatalogProduct] | None = None,
        error: CatalogUnavailableError | None = None,
    ) -> None:
        self.products = products or []
        self.error = error
        self.calls = 0

    def search(self, query: str) -> list[CatalogProduct]:
        assert query == "Example"
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.products


class FakeResponse:
    status_code = 200

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self._payload


class FakeHttpClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests: list[dict[str, Any]] = []

    def post(self, path: str, **kwargs: object) -> FakeResponse:
        self.requests.append({"path": path, **kwargs})
        return FakeResponse(self.payload)

    def close(self) -> None:
        pass


def test_catalog_skips_fallback_when_primary_has_ingredients() -> None:
    primary = FakeCatalog([_product(ingredients="Oats, cocoa")])
    secondary = FakeCatalog([_product(ingredients="Different")])
    catalog = FallbackProductCatalog(primary, secondary)

    result = catalog.search("Example")

    assert result[0].ingredients_text == "Oats, cocoa"
    assert primary.calls == 1
    assert secondary.calls == 0


def test_catalog_uses_secondary_ingredients_with_secondary_provenance() -> None:
    primary = FakeCatalog([_product(ingredients=None)])
    usda_product = _product(ingredients="Corn, salt", source_name="USDA FoodData Central")
    secondary = FakeCatalog([usda_product])
    catalog = FallbackProductCatalog(primary, secondary)

    result = catalog.search("Example")

    assert len(result) == 1
    assert result[0].ingredients_text == "Corn, salt"
    assert result[0].image_url == "https://images.example/snack.jpg"
    assert result[0].source_name == "Open Food Facts"
    assert result[0].ingredients_source_name == "USDA FoodData Central"
    assert result[0].ingredients_source_url == "https://example.test/product"


def test_catalog_does_not_append_unmatched_secondary_products() -> None:
    primary = FakeCatalog([_product(ingredients=None)])
    secondary_product = replace(
        _product(ingredients="Corn", source_name="USDA FoodData Central"),
        barcode="999999999999",
    )
    catalog = FallbackProductCatalog(primary, FakeCatalog([secondary_product]))

    result = catalog.search("Example")

    assert len(result) == 1
    assert result[0].barcode == "012345678905"


def test_catalog_marks_secondary_results_degraded_when_primary_is_unavailable() -> None:
    primary = FakeCatalog(error=CatalogUnavailableError("Open Food Facts unavailable"))
    secondary = FakeCatalog(
        [_product(ingredients="Corn", source_name="USDA FoodData Central")]
    )
    catalog = FallbackProductCatalog(primary, secondary)

    result = catalog.search("Example")

    assert result[0].catalog_degraded is True
    assert result[0].source_name == "USDA FoodData Central"


def test_usda_maps_branded_food_ingredients_and_gtin() -> None:
    client = FakeHttpClient(
        {
            "foods": [
                {
                    "fdcId": 123,
                    "description": "example snack",
                    "brandName": "Example",
                    "brandOwner": "Example Foods Inc.",
                    "gtinUpc": "012345678905",
                    "ingredients": "CORN, SALT",
                    "publishedDate": "2026-01-15",
                }
            ]
        }
    )
    catalog = UsdaFoodDataCatalog(
        "unused",
        "https://api.nal.usda.gov/fdc/v1",
        8,
        client=client,
    )

    result = catalog.search("Example")

    assert result[0].barcode == "012345678905"
    assert result[0].ingredients_text == "CORN, SALT"
    assert result[0].source_name == "USDA FoodData Central"
    assert result[0].brand_owner == "Example Foods Inc."
    assert client.requests[0]["path"] == "/foods/search"
    assert client.requests[0]["params"] == {"api_key": "unused"}
