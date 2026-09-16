from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import httpx2 as httpx


class CatalogUnavailableError(Exception):
    """Raised when the external product catalog cannot answer safely."""


@dataclass(frozen=True, slots=True)
class CatalogProduct:
    barcode: str
    name: str
    brand: str | None
    image_url: str | None
    ingredients_analysis_tags: frozenset[str]
    environmental_score_grade: str | None
    last_updated_at: datetime | None
    source_url: str


class ProductCatalog(Protocol):
    def search(self, query: str) -> list[CatalogProduct]: ...


class OpenFoodFactsCatalog:
    _FIELDS = ",".join(
        (
            "code",
            "product_name",
            "product_name_pt",
            "product_name_en",
            "brands",
            "image_front_small_url",
            "ingredients_analysis_tags",
            "environmental_score_grade",
            "ecoscore_grade",
            "last_modified_t",
        )
    )

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: float,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def search(self, query: str) -> list[CatalogProduct]:
        normalized_query = query.strip()
        if _looks_like_barcode(normalized_query):
            return self._get_by_barcode(normalized_query)
        return self._search_by_text(normalized_query)

    def _get_by_barcode(self, barcode: str) -> list[CatalogProduct]:
        payload = self._get_json(
            f"/api/v3.6/product/{barcode}.json",
            params={"fields": self._FIELDS},
            allow_not_found=True,
        )
        product_payload = payload.get("product")
        if not isinstance(product_payload, Mapping):
            return []
        product = self._to_product(product_payload)
        return [product] if product is not None else []

    def _search_by_text(self, query: str) -> list[CatalogProduct]:
        payload = self._get_json(
            "/cgi/search.pl",
            params={
                "search_terms": query,
                "search_simple": "1",
                "action": "process",
                "json": "1",
                "page_size": "8",
                "fields": self._FIELDS,
            },
        )
        products_payload = payload.get("products")
        if not isinstance(products_payload, list):
            return []

        products: list[CatalogProduct] = []
        for item in products_payload:
            if isinstance(item, Mapping):
                product = self._to_product(item)
                if product is not None:
                    products.append(product)
        return products

    def _get_json(
        self,
        path: str,
        params: dict[str, str],
        *,
        allow_not_found: bool = False,
    ) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
            if allow_not_found and response.status_code == 404:
                return {}
            response.raise_for_status()
            payload = cast(object, response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise CatalogUnavailableError(
                "Open Food Facts is temporarily unavailable. Please try again shortly."
            ) from error

        if not isinstance(payload, dict):
            raise CatalogUnavailableError("Open Food Facts returned an unexpected response.")
        return cast(dict[str, Any], payload)

    def _to_product(self, payload: Mapping[object, object]) -> CatalogProduct | None:
        barcode = _read_text(payload, "code")
        if barcode is None:
            return None

        name = (
            _read_text(payload, "product_name_pt")
            or _read_text(payload, "product_name")
            or _read_text(payload, "product_name_en")
            or "Unnamed product"
        )
        environmental_grade = _read_text(payload, "environmental_score_grade")
        if environmental_grade is None:
            environmental_grade = _read_text(payload, "ecoscore_grade")

        return CatalogProduct(
            barcode=barcode,
            name=name,
            brand=_read_text(payload, "brands"),
            image_url=_read_text(payload, "image_front_small_url"),
            ingredients_analysis_tags=_read_tags(payload, "ingredients_analysis_tags"),
            environmental_score_grade=environmental_grade,
            last_updated_at=_read_timestamp(payload, "last_modified_t"),
            source_url=f"{self._base_url}/product/{barcode}",
        )


def _looks_like_barcode(query: str) -> bool:
    return query.isdigit() and 8 <= len(query) <= 14


def _read_text(payload: Mapping[object, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int):
        return str(value)
    return None


def _read_tags(payload: Mapping[object, object], key: str) -> frozenset[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item.lower() for item in value if isinstance(item, str))


def _read_timestamp(payload: Mapping[object, object], key: str) -> datetime | None:
    value = payload.get(key)
    if not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except OverflowError, OSError, ValueError:
        return None
