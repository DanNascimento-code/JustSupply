import re

from justsupply.domain.rag import TextChunk

PAGE_MARKER = re.compile(r"(?m)^\[Page (?P<number>\d+)\]\s*$")


def chunk_document(
    text: str,
    *,
    target_characters: int,
    overlap_characters: int,
) -> list[TextChunk]:
    if target_characters < 100:
        raise ValueError("The chunk target must be at least 100 characters.")
    if overlap_characters < 0 or overlap_characters >= target_characters:
        raise ValueError("The chunk overlap must be smaller than the chunk target.")

    sections = _page_sections(text)
    chunks: list[TextChunk] = []
    for page_number, section_text in sections:
        for start, end, content in _split_section(
            section_text,
            target_characters=target_characters,
            overlap_characters=overlap_characters,
        ):
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    text=content,
                    page_number=page_number,
                    character_start=start,
                    character_end=end,
                )
            )
    return chunks


def _page_sections(text: str) -> list[tuple[int | None, str]]:
    markers = list(PAGE_MARKER.finditer(text))
    if not markers:
        return [(None, text.strip())]

    sections: list[tuple[int | None, str]] = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        page_text = text[start:end].strip()
        if page_text:
            sections.append((int(marker.group("number")), page_text))
    return sections


def _split_section(
    text: str,
    *,
    target_characters: int,
    overlap_characters: int,
) -> list[tuple[int, int, str]]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []

    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(normalized):
        proposed_end = min(start + target_characters, len(normalized))
        end = _nearest_boundary(normalized, start, proposed_end)
        content = normalized[start:end].strip()
        if content:
            chunks.append((start, end, content))
        if end >= len(normalized):
            break
        next_start = max(0, end - overlap_characters)
        while next_start < end and not normalized[next_start].isspace():
            next_start += 1
        start = next_start + 1 if next_start < end else end
    return chunks


def _nearest_boundary(text: str, start: int, proposed_end: int) -> int:
    if proposed_end >= len(text):
        return len(text)
    minimum_end = start + max(1, (proposed_end - start) // 2)
    for separator in ("\n\n", ". ", "; ", " "):
        boundary = text.rfind(separator, minimum_end, proposed_end)
        if boundary != -1:
            return boundary + len(separator.rstrip())
    return proposed_end
