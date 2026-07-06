import fitz

from app.utils.pdf_parser import extract_pages


def _make_pdf(path: str, pages_text: list[str]) -> None:
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_pdf_parser_extracts_text(tmp_path):
    pdf_path = str(tmp_path / "sample.pdf")
    _make_pdf(pdf_path, ["Check the battery terminals weekly.", "Replace the oil filter."])

    pages = extract_pages(pdf_path)

    assert [number for number, _ in pages] == [1, 2]
    assert "battery terminals" in pages[0][1]
    assert "oil filter" in pages[1][1]
