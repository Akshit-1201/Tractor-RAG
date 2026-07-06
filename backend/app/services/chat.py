"""Chat service (spec §8.4, §8.5, §9.4): grounded generation, citation parsing,
the two-layer "I don't know" guarantee, and the three-gate image logic.
"""

import re
import time
from dataclasses import dataclass
from typing import Iterator, Optional

from app.config import settings
from app.core.prompts import IDK_MESSAGE, SYSTEM_PROMPT
from app.services import analytics, condense, retrieval
from app.services.embeddings import get_client
from app.services.retrieval import RetrievedChunk


@dataclass
class ChatResult:
    answer: str
    is_answered: bool
    sources: list[dict]
    image: Optional[dict]


def format_numbered_context(chunks: list[RetrievedChunk]) -> str:
    return "\n".join(f"[{i}] {chunk.content}" for i, chunk in enumerate(chunks, start=1))


def parse_answer_and_citations(raw: str) -> tuple[str, list[int]]:
    """Split off the trailing `CITED: [...]` line. No CITED line found → no
    citations (conservative: uncited answers get no sources and no image)."""
    lines = raw.rstrip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip().upper().startswith("CITED:"):
            numbers = [int(n) for n in re.findall(r"\d+", lines[index])]
            answer = "\n".join(lines[:index]).rstrip()
            return answer, numbers
    return raw.strip(), []


def map_numbers_to_chunk_ids(numbers: list[int], chunks: list[RetrievedChunk]) -> list[int]:
    """1-based source numbers → chunk ids; out-of-range numbers are dropped."""
    return [chunks[n - 1].id for n in numbers if 1 <= n <= len(chunks)]


def _normalize(text: str) -> str:
    return text.replace("’", "'").strip().casefold()


_IDK_NORMALIZED = _normalize(IDK_MESSAGE).rstrip(".")


def is_idk(answer_text: str) -> bool:
    """Normalized full-phrase containment — never strict equality (spec §8.5).
    Catches drift on apostrophes/punctuation and politeness prefixes such as
    "I'm sorry, I don't have information..."; the full canonical phrase cannot
    false-positive on legitimate answers."""
    return _IDK_NORMALIZED in _normalize(answer_text)


def select_image(
    chunks: list[RetrievedChunk], cited_chunk_ids: list[int], is_answered: bool
) -> Optional[dict]:
    """The image gate, Option A (spec §9.4). `chunk.score` is dense cosine
    similarity — never the RRF ordering score. When in doubt, show no image."""
    if not is_answered:  # Gate 1 — never alongside "I don't know"
        return None
    candidates = [
        c
        for c in chunks
        if c.source_type == "image"
        and c.id in cited_chunk_ids  # Gate 2 (Option A): the LLM actually used it
        and c.score >= settings.IMAGE_SIMILARITY_THRESHOLD  # Gate 3: confidence floor
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c.score)
    return {"url": best.metadata["image_url"], "caption": best.metadata.get("source_name")}


def build_sources(chunks: list[RetrievedChunk], cited_chunk_ids: list[int]) -> list[dict]:
    cited = set(cited_chunk_ids)
    return [
        {"type": c.source_type, "name": c.metadata.get("source_name", ""), "chunk_id": c.id}
        for c in chunks
        if c.id in cited
    ]


def _llm_answer(context: str, query: str) -> str:
    response = get_client().chat.completions.create(
        model=settings.CHAT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nQuestion: {query}"},
        ],
    )
    return response.choices[0].message.content or ""


def stream_llm(context: str, query: str) -> Iterator[str]:
    """Token stream for SSE mode; the router strips the CITED trailer."""
    stream = get_client().chat.completions.create(
        model=settings.CHAT_MODEL,
        temperature=0,
        stream=True,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nQuestion: {query}"},
        ],
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def finalize(
    query: str, chunks: list[RetrievedChunk], raw: str, started: float
) -> ChatResult:
    """Shared tail of both modes: parse, enforce the IDK guarantee, gate the
    image, build sources, log analytics."""
    answer_text, cited_numbers = parse_answer_and_citations(raw)
    cited_chunk_ids = map_numbers_to_chunk_ids(cited_numbers, chunks)
    # a blank model response is never a confident answer
    is_answered = bool(answer_text.strip()) and not is_idk(answer_text)
    if not is_answered:
        answer_text = IDK_MESSAGE  # always return the canonical string verbatim
        cited_chunk_ids = []  # an IDK response never carries sources or an image

    image = select_image(chunks, cited_chunk_ids, is_answered)
    sources = build_sources(chunks, cited_chunk_ids)

    analytics.log(
        query,
        answer_text,
        is_answered,
        retrieved=[c.id for c in chunks],
        cited=cited_chunk_ids,
        image_shown=image is not None,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    return ChatResult(answer=answer_text, is_answered=is_answered, sources=sources, image=image)


def resolve_standalone(query: str, history: Optional[list[dict]]) -> str:
    """Follow-up understanding: reformulate a context-dependent question into a
    standalone one using recent history. Turn 1 (no history) is unchanged, so it
    carries zero added cost. History only shapes retrieval and the phrasing of the
    grounded question — it is never a source, so the IDK guarantee is preserved."""
    if not history:
        return query
    return condense.condense_query(history, query)


def answer_question(query: str, history: Optional[list[dict]] = None) -> ChatResult:
    """JSON-mode orchestration (spec §8.4), with follow-up query resolution."""
    started = time.perf_counter()
    standalone = resolve_standalone(query, history)
    chunks = retrieval.retrieve(standalone)
    if not chunks:  # empty corpus: nothing to ground on — skip the LLM call
        return finalize(query, [], f"{IDK_MESSAGE}\nCITED: []", started)
    raw = _llm_answer(format_numbered_context(chunks), standalone)
    # analytics logs the original question the customer typed, not the rewrite
    return finalize(query, chunks, raw, started)
