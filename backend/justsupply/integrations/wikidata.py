import unicodedata
from collections.abc import Mapping
from typing import Any, cast

import httpx2 as httpx

from justsupply.domain.research import GroundedWebSource, OrganizationLookup

_ORGANIZATION_DESCRIPTION_TERMS = {
    "brand",
    "company",
    "corporation",
    "manufacturer",
    "organization",
}
_RELATION_PROPERTIES = ("P127", "P749", "P176")  # owner, parent organization, manufacturer


class WikidataOrganizationResolver:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: float,
        *,
        client: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url,
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def resolve(self, brand: str | None, brand_owner: str | None) -> OrganizationLookup:
        seed_names = _unique_names((brand_owner,))
        query = _primary_name(brand)
        if query is None:
            return OrganizationLookup(names=seed_names)
        try:
            candidate = self._find_candidate(query)
            if candidate is None:
                return OrganizationLookup(names=seed_names)
            entity_id, label, description = candidate
            related_ids = self._related_entity_ids(entity_id)
            related_names = self._entity_labels(related_ids)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return OrganizationLookup(names=seed_names)

        names = _unique_names((*seed_names, *related_names))
        if not names:
            return OrganizationLookup(names=())
        relation_text = ", ".join(names)
        description_text = f" ({description})" if description else ""
        return OrganizationLookup(
            names=names,
            source=GroundedWebSource(
                number=0,
                title=f"{label} — Wikidata organization record",
                provider_name="Wikidata",
                url=f"{self._base_url}/wiki/{entity_id}",
                cited_text=(
                    f"Wikidata identifies {label}{description_text} and links the entity through "
                    f"owner, parent-organization, or manufacturer statements to: {relation_text}."
                ),
                focus="organization",
                source_class="public_database",
            ),
        )

    def close(self) -> None:
        self._client.close()

    def _find_candidate(self, query: str) -> tuple[str, str, str | None] | None:
        payload = self._get_json(
            "/w/api.php",
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                "limit": "5",
                "type": "item",
            },
        )
        search = payload.get("search")
        if not isinstance(search, list):
            return None
        exact: list[tuple[str, str, str | None]] = []
        for item in search:
            if not isinstance(item, Mapping):
                continue
            entity_id = item.get("id")
            label = item.get("label")
            description = item.get("description")
            if not isinstance(entity_id, str) or not isinstance(label, str):
                continue
            if _normalize(label) != _normalize(query):
                continue
            exact.append(
                (
                    entity_id,
                    label,
                    description if isinstance(description, str) else None,
                )
            )
        if not exact:
            return None
        for candidate in exact:
            description = (candidate[2] or "").casefold()
            if any(term in description for term in _ORGANIZATION_DESCRIPTION_TERMS):
                return candidate
        return exact[0]

    def _related_entity_ids(self, entity_id: str) -> tuple[str, ...]:
        payload = self._get_json(f"/wiki/Special:EntityData/{entity_id}.json", {})
        entities = payload.get("entities")
        if not isinstance(entities, Mapping):
            return ()
        entity = entities.get(entity_id)
        if not isinstance(entity, Mapping):
            return ()
        claims = entity.get("claims")
        if not isinstance(claims, Mapping):
            return ()
        related: list[str] = []
        for property_id in _RELATION_PROPERTIES:
            statements = claims.get(property_id)
            if not isinstance(statements, list):
                continue
            for statement in statements:
                related_id = _statement_entity_id(statement)
                if related_id and related_id not in related:
                    related.append(related_id)
        return tuple(related[:5])

    def _entity_labels(self, entity_ids: tuple[str, ...]) -> tuple[str, ...]:
        if not entity_ids:
            return ()
        payload = self._get_json(
            "/w/api.php",
            {
                "action": "wbgetentities",
                "ids": "|".join(entity_ids),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
        )
        entities = payload.get("entities")
        if not isinstance(entities, Mapping):
            return ()
        labels: list[str] = []
        for entity_id in entity_ids:
            entity = entities.get(entity_id)
            if not isinstance(entity, Mapping):
                continue
            entity_labels = entity.get("labels")
            if not isinstance(entity_labels, Mapping):
                continue
            english = entity_labels.get("en")
            if isinstance(english, Mapping):
                value = english.get("value")
                if isinstance(value, str) and value.strip():
                    labels.append(value.strip())
        return tuple(labels)

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, object]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        payload = cast(object, response.json())
        if not isinstance(payload, dict):
            raise ValueError("Wikidata returned an unexpected response.")
        return cast(dict[str, object], payload)


def _statement_entity_id(statement: object) -> str | None:
    if not isinstance(statement, Mapping):
        return None
    mainsnak = statement.get("mainsnak")
    if not isinstance(mainsnak, Mapping):
        return None
    datavalue = mainsnak.get("datavalue")
    if not isinstance(datavalue, Mapping):
        return None
    value = datavalue.get("value")
    if not isinstance(value, Mapping):
        return None
    entity_id = value.get("id")
    return entity_id if isinstance(entity_id, str) else None


def _primary_name(names: str | None) -> str | None:
    if names is None:
        return None
    value = names.split(",", maxsplit=1)[0].strip()
    return value or None


def _unique_names(values: tuple[str | None, ...]) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        clean = value.strip()
        key = _normalize(clean)
        if clean and key not in seen:
            seen.add(key)
            names.append(clean)
    return tuple(names)


def _normalize(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character) and character.isalnum()
    )
