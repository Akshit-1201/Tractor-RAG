"""Chunking (spec §8.1 step 3): pack paragraph blocks up to a token target with
word overlap between consecutive chunks. Token counts are estimated (~1.3 tokens
per English word) — the spec targets a range (500–800), not exact counts, so an
estimate avoids a tokenizer dependency.
"""

import re

_TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * _TOKENS_PER_WORD))


def _split_blocks(text: str) -> list[str]:
    """Paragraph/heading boundaries: blank-line separated blocks."""
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def chunk_text(text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    # Normalize into units no larger than the target (oversized blocks get word-split),
    # then greedily pack units, seeding each new chunk with overlap from the last.
    words_per_unit = max(1, int(target_tokens / _TOKENS_PER_WORD))
    units: list[str] = []
    for block in _split_blocks(text):
        if estimate_tokens(block) <= target_tokens:
            units.append(block)
        else:
            words = block.split()
            units.extend(
                " ".join(words[i : i + words_per_unit])
                for i in range(0, len(words), words_per_unit)
            )

    overlap_words = max(0, int(overlap_tokens / _TOKENS_PER_WORD))
    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n\n".join(current + [unit])
        if current and estimate_tokens(candidate) > target_tokens:
            chunks.append("\n\n".join(current))
            tail = " ".join(chunks[-1].split()[-overlap_words:]) if overlap_words else ""
            current = [tail, unit] if tail else [unit]
        else:
            current.append(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_pages(
    pages: list[tuple[int, str]],
    source_name: str,
    target_tokens: int,
    overlap_tokens: int,
) -> list[dict]:
    """Chunk per page (pages are natural boundaries; overlap never crosses them).

    Returns [{"content": str, "metadata": {"source_name": ..., "page": ...}}].
    """
    out: list[dict] = []
    for page_number, text in pages:
        for piece in chunk_text(text, target_tokens, overlap_tokens):
            out.append(
                {
                    "content": piece,
                    "metadata": {"source_name": source_name, "page": page_number},
                }
            )
    return out
