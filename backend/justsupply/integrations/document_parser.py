from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class DocumentValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    media_type: str
    text: str


ALLOWED_MEDIA_TYPES = {
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


def parse_document(
    filename: str,
    content_type: str | None,
    content: bytes,
    *,
    max_bytes: int,
    max_characters: int,
) -> ParsedDocument:
    safe_filename = Path(filename).name.strip()
    suffix = Path(safe_filename).suffix.lower()
    expected_media_type = ALLOWED_MEDIA_TYPES.get(suffix)

    if not safe_filename or expected_media_type is None:
        raise DocumentValidationError("Upload a PDF, TXT, or Markdown document.")
    if not content:
        raise DocumentValidationError("The uploaded document is empty.")
    if len(content) > max_bytes:
        maximum_mb = max_bytes // (1024 * 1024)
        raise DocumentValidationError(f"The document must be {maximum_mb} MB or smaller.")
    if content_type not in {None, "", expected_media_type, "application/octet-stream"}:
        raise DocumentValidationError("The file content type does not match its extension.")

    text = _extract_pdf_text(content) if suffix == ".pdf" else _decode_text(content)
    normalized_text = text.strip()
    if len(normalized_text) < 40:
        raise DocumentValidationError(
            "The document does not contain enough readable text. Scanned PDFs need OCR first."
        )
    if len(normalized_text) > max_characters:
        raise DocumentValidationError(
            "The extracted text is too long for this MVP. Upload a shorter document."
        )

    return ParsedDocument(
        filename=safe_filename,
        media_type=expected_media_type,
        text=normalized_text,
    )


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentValidationError("Text documents must use UTF-8 encoding.") from error


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if page_text:
                pages.append(f"[Page {page_number}]\n{page_text}")
        return "\n\n".join(pages)
    except (PdfReadError, OSError, ValueError) as error:
        raise DocumentValidationError("The PDF could not be read.") from error
