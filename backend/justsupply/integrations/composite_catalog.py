from dataclasses import replace

from justsupply.integrations.open_food_facts import (
    CatalogProduct,
    CatalogUnavailableError,
    ProductCatalog,
)


class FallbackProductCatalog:
    """Use a secondary catalog only when primary ingredient coverage is weak."""

    def __init__(self, primary: ProductCatalog, secondary: ProductCatalog | None = None) -> None:
        self._primary = primary
        self._secondary = secondary

    def close(self) -> None:
        for provider in (self._primary, self._secondary):
            close = getattr(provider, "close", None)
            if callable(close):
                close()

    def search(self, query: str) -> list[CatalogProduct]:
        primary_error: CatalogUnavailableError | None = None
        try:
            primary_products = self._primary.search(query)
        except CatalogUnavailableError as error:
            primary_error = error
            primary_products = []

        needs_fallback = not primary_products or any(
            not product.ingredients_text for product in primary_products
        )
        if self._secondary is None or not needs_fallback:
            if primary_error is not None:
                raise primary_error
            return primary_products

        try:
            secondary_products = self._secondary.search(query)
        except CatalogUnavailableError as secondary_error:
            if primary_error is not None:
                raise primary_error from secondary_error
            return primary_products
        if primary_error is not None:
            return [replace(product, catalog_degraded=True) for product in secondary_products]
        return _merge_products(primary_products, secondary_products)


def _merge_products(
    primary_products: list[CatalogProduct],
    secondary_products: list[CatalogProduct],
) -> list[CatalogProduct]:
    merged = list(primary_products)
    by_barcode = {product.barcode: index for index, product in enumerate(merged)}
    for secondary in secondary_products:
        index = by_barcode.get(secondary.barcode)
        if index is None:
            if not primary_products:
                by_barcode[secondary.barcode] = len(merged)
                merged.append(secondary)
            continue
        primary = merged[index]
        if primary.ingredients_text:
            continue
        merged[index] = replace(
            primary,
            ingredients_text=secondary.ingredients_text,
            brand_owner=primary.brand_owner or secondary.brand_owner,
            ingredients_source_url=secondary.source_url,
            ingredients_source_name=secondary.source_name,
        )
    return merged
