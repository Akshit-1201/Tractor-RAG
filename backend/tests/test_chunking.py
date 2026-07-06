from app.utils.chunking import chunk_pages, chunk_text, estimate_tokens

_PARAGRAPH = (
    "The hydraulic system requires regular fluid checks and filter replacement "
    "at the intervals listed in the maintenance schedule for this tractor model."
)


def test_chunking_bounds():
    text = "\n\n".join(_PARAGRAPH for _ in range(120))  # ~2700 estimated tokens
    chunks = chunk_text(text, target_tokens=650, overlap_tokens=80)

    assert len(chunks) >= 2
    for chunk in chunks:
        # target plus the overlap seed and one paragraph of slack
        assert estimate_tokens(chunk) <= 650 + 2 * 80


def test_chunking_overlap_carries_tail():
    text = "\n\n".join(f"Paragraph {i}: {_PARAGRAPH}" for i in range(120))
    chunks = chunk_text(text, target_tokens=650, overlap_tokens=80)

    for previous, following in zip(chunks, chunks[1:]):
        tail = " ".join(previous.split()[-5:])
        assert tail in following  # the next chunk starts with the previous tail


def test_oversized_block_is_split():
    one_giant_block = " ".join(f"word{i}" for i in range(3000))  # no paragraph breaks
    chunks = chunk_text(one_giant_block, target_tokens=650, overlap_tokens=80)
    assert len(chunks) > 1
    for chunk in chunks:
        assert estimate_tokens(chunk) <= 650 + 2 * 80


def test_chunk_pages_attaches_metadata():
    pages = [(1, "\n\n".join(_PARAGRAPH for _ in range(60))), (2, _PARAGRAPH)]
    chunks = chunk_pages(pages, source_name="manual.pdf", target_tokens=650, overlap_tokens=80)

    assert all(c["metadata"]["source_name"] == "manual.pdf" for c in chunks)
    assert {c["metadata"]["page"] for c in chunks} == {1, 2}
    # overlap never crosses a page boundary: page-2 content stays on page 2
    page_two = [c for c in chunks if c["metadata"]["page"] == 2]
    assert len(page_two) == 1
