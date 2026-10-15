"""Read the first few pages of a file as plain text.

Classification only needs the opening of a document - the title block, the
"Assignment 2, due 12 Oct" line, the question paper header - so we never
read whole files. That keeps scans of big lecture PDFs fast.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from contextos.ingest import ocr

MAX_PAGES = 3
MAX_CHARS = 6000
# Below this much text, a PDF is treated as a scan and OCR'd.
MIN_TEXT_CHARS = 50


@dataclass
class Extracted:
    text: str
    # pdf | ocr | ocr_unavailable | docx | pptx | image | none
    method: str
    # Document title from file metadata, when the author set a real one.
    meta_title: str | None = None
    error: str | None = None


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:MAX_CHARS]


def extract(path: Path) -> Extracted:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _pdf(path)
        if suffix == ".docx":
            return _docx(path)
        if suffix == ".pptx":
            return _pptx(path)
        if suffix in {".jpg", ".jpeg", ".png"}:
            if not ocr.ocr_available():
                return Extracted("", "ocr_unavailable")
            return Extracted(_clean(ocr.ocr_image(path)), "image")
    except Exception as e:  # a corrupt file must not stop the whole scan
        return Extracted("", "none", error=f"could not read file: {e}")
    return Extracted("", "none")


def _pdf(path: Path) -> Extracted:
    import pymupdf

    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            return Extracted("", "none", error="PDF is password-protected")
        meta_title = (doc.metadata or {}).get("title") or None
        pages = doc.pages(0, min(MAX_PAGES, doc.page_count))
        text = _clean("\n".join(page.get_text() for page in pages))

    if len(text) >= MIN_TEXT_CHARS:
        return Extracted(text, "pdf", meta_title)
    if not ocr.ocr_available():
        return Extracted(text, "ocr_unavailable", meta_title)
    return Extracted(_clean(ocr.ocr_pdf(path)), "ocr", meta_title)


def _docx(path: Path) -> Extracted:
    import docx

    d = docx.Document(str(path))
    lines = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables[:3]:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return Extracted(_clean("\n".join(lines)), "docx", d.core_properties.title or None)


def _pptx(path: Path) -> Extracted:
    import pptx

    deck = pptx.Presentation(str(path))
    lines = []
    for slide in list(deck.slides)[:8]:
        for shape in slide.shapes:
            if shape.has_text_frame:
                lines.append(shape.text_frame.text)
    return Extracted(_clean("\n".join(lines)), "pptx", deck.core_properties.title or None)
