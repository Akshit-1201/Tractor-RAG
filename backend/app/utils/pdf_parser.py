"""PyMuPDF text extraction (spec §8.1 step 2)."""

import fitz  # PyMuPDF


def extract_pages(file_path: str) -> list[tuple[int, str]]:
    """Return [(page_number, text)] with 1-based page numbers."""
    with fitz.open(file_path) as doc:
        return [(number + 1, page.get_text()) for number, page in enumerate(doc)]
