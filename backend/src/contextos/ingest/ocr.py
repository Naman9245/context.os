"""OCR for scanned PDFs and photos, via the Tesseract binary.

Tesseract is a system package (`sudo apt install tesseract-ocr`), not a pip
one. Everything here degrades to "no text" when it is missing, and the
caller records `ocr_unavailable` so the UI can say why.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_pdf(path: Path, max_pages: int = 2, dpi: int = 200) -> str:
    import pymupdf
    import pytesseract
    from PIL import Image

    parts = []
    with pymupdf.open(path) as doc:
        for page in doc.pages(0, min(max_pages, doc.page_count)):
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            parts.append(pytesseract.image_to_string(img))
    return "\n".join(parts)


def ocr_image(path: Path) -> str:
    import pytesseract
    from PIL import Image

    with Image.open(path) as img:
        return pytesseract.image_to_string(img.convert("L"))
