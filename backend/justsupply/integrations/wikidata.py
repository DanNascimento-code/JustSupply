import unicodedata
from collections.abc import Mapping
from typing import Any, cast

import httpx2 as httpx

from justsupply.domain.research import GroundedWebSource, OrganizationLookup

_ORGANIZATION_DESCRIPTION_TERMS = {
    "brand",
    "business",
    "company",
    "corporation",
    "empresa",
    "food",
    "manufacturer",
    "organization",
    "subsidiary",
}
_CONSUMER_BUSINESS_TERMS = {"beverage", "consumer", "dairy", "food", "manufacturer", "retail"}
_NON_ORGANIZATION_TERMS = {
    "family name",
    "given name",
    "software",
    "video game",
    "sports club",
    "person",
}
_RELATION_PROPERTIES = ("P127", "P749", "P176")  # owner, parent organization, manufacturer
_JURISDICTION_PROPERTIES = ("P17", "P495")  # country, country of origin
_OFFICIAL_NAME_PROPERTY = "P1448"


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
            related_ids, jurisdiction_ids, official_names = self._entity_details(entity_id)
            labels = self._entity_labels((*related_ids, *jurisdiction_ids))
            related_names = tuple(
                labels[related_id] for related_id in related_ids if related_id in labels
            )
            jurisdiction_names = tuple(
                labels[jurisdiction_id]
                for jurisdiction_id in jurisdiction_ids
                if jurisdiction_id in labels
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return OrganizationLookup(names=seed_names)

        candidate_name = label if _normalize(label) != _normalize(query) else None
        names = _unique_names(
            (*seed_names, candidate_name, *official_names, *related_names)
        )
        if not names:
            return OrganizationLookup(names=())
        relation_text = ", ".join(names)
        jurisdiction = jurisdiction_names[0] if jurisdiction_names else None
        description_text = f" ({description})" if description else ""
        return OrganizationLookup(
            names=names,
            jurisdiction=jurisdiction,
            source=GroundedWebSource(
                number=0,
                title=f"{label} — Wikidata organization record",
                provider_name="Wikidata",
                url=f"{self._base_url}/wiki/{entity_id}",
                cited_text=(
                    f"Wikidata identifies {label}{description_text} and links the entity through "
                    f"owner, parent-organization, manufacturer, or official-name statements "
                    f"to: {relation_text}. Reporting jurisdiction: "
                    f"{jurisdiction or 'not stated in the record'}."
                ),
                focus="organization",
                source_class="public_database",
            ),
        )

    def close(self) -> None:
        self._client.close()

    def _find_candidate(self, query: str) -> tuple[str, str, str | None] | None:
        candidates: list[tuple[int, tuple[str, str, str | None]]] = []
        query_key = _normalize(query)
        for language in ("en", "pt", "es"):
            payload = self._get_json(
                "/w/api.php",
                {
                    "action": "wbsearchentities",
                    "search": query,
                    "language": language,
                    "format": "json",
                    "limit": "10",
                    "type": "item",
                },
            )
            search = payload.get("search")
            if not isinstance(search, list):
                continue
            for item in search:
                if not isinstance(item, Mapping):
                    continue
                entity_id = item.get("id")
                label = item.get("label")
                description = item.get("description")
                if not isinstance(entity_id, str) or not isinstance(label, str):
                    continue
                description_text = description if isinstance(description, str) else None
                score = _candidate_score(label, description_text, query_key)
                if score < 0:
                    continue
                candidate = (entity_id, label, description_text)
                if candidate not in (existing[1] for existing in candidates):
                    candidates.append((score, candidate))
            if candidates and max(score for score, _ in candidates) >= 16:
                break
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1] if candidates[0][0] >= 15 else None

    def _entity_details(
        self, entity_id: str
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        payload = self._get_json(f"/wiki/Special:EntityData/{entity_id}.json", {})
        entities = payload.get("entities")
        if not isinstance(entities, Mapping):
            return (), (), ()
        entity = entities.get(entity_id)
        if not isinstance(entity, Mapping):
            return (), (), ()
        claims = entity.get("claims")
        if not isinstance(claims, Mapping):
            return (), (), ()
        related: list[str] = []
        for property_id in _RELATION_PROPERTIES:
            statements = claims.get(property_id)
            if not isinstance(statements, list):
                continue
            for statement in statements:
                related_id = _statement_entity_id(statement)
                if related_id and related_id not in related:
                    related.append(related_id)
        jurisdictions: list[str] = []
        for property_id in _JURISDICTION_PROPERTIES:
            statements = claims.get(property_id)
            if not isinstance(statements, list):
                continue
            for statement in statements:
                jurisdiction_id = _statement_entity_id(statement)
                if jurisdiction_id and jurisdiction_id not in jurisdictions:
                    jurisdictions.append(jurisdiction_id)
        official_names: list[str] = []
        statements = claims.get(_OFFICIAL_NAME_PROPERTY)
        if isinstance(statements, list):
            for statement in statements:
                official_name = _statement_text(statement)
                if official_name and official_name not in official_names:
                    official_names.append(official_name)
        return tuple(related[:5]), tuple(jurisdictions[:2]), tuple(official_names[:3])

    def _entity_labels(self, entity_ids: tuple[str, ...]) -> dict[str, str]:
        if not entity_ids:
            return {}
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
            return {}
        labels: dict[str, str] = {}
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
                    labels[entity_id] = value.strip()
        return labels

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


def _statement_text(statement: object) -> str | None:
    if not isinstance(statement, Mapping):
        return None
    mainsnak = statement.get("mainsnak")
    if not isinstance(mainsnak, Mapping):
        return None
    datavalue = mainsnak.get("datavalue")
    if not isinstance(datavalue, Mapping):
        return None
    value = datavalue.get("value")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _primary_name(names: str | None) -> str | None:
    if names is None:
        return None
    value = names.split(",", maxsplit=1)[0].strip()
    return value or None


def _candidate_score(label: str, description: str | None, query_key: str) -> int:
    label_key = _normalize(label)
    base_key = _company_base(label)
    if label_key == query_key:
        score = 10
    elif base_key == query_key:
        score = 8
    else:
        return -1
    description_text = (description or "").casefold()
    if any(term in description_text for term in _NON_ORGANIZATION_TERMS):
        return -1
    if any(term in description_text for term in _ORGANIZATION_DESCRIPTION_TERMS):
        score += 5
    if any(term in description_text for term in _CONSUMER_BUSINESS_TERMS):
        score += 3
    return score


def _company_base(value: str) -> str:
    key = _normalize(value)
    suffixes = (
        "corporation",
        "company",
        "limited",
        "holdings",
        "holding",
        "group",
        "corp",
        "ltd",
        "inc",
        "sa",
    )
    for suffix in suffixes:
        if key.endswith(suffix) and len(key) - len(suffix) >= 3:
            return key[: -len(suffix)]
    return key


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
