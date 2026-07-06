"""Hybrid retrieval (spec §8.3): dense (pgvector cosine) + lexical (Postgres FTS),
fused with Reciprocal Rank Fusion.

Score semantics (critical for the image gate): every chunk's `score` is its
**dense cosine similarity** to the query — both SQL branches return it. RRF is
used ONLY to order the fused list; RRF's own ~0.03-scale values are never
exposed, because Gate 3 compares `score` against IMAGE_SIMILARITY_THRESHOLD.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.services import embeddings

_RRF_K = 60  # standard RRF constant

# `, id` is a stable tiebreaker: when two chunks have identical scores, ordering
# must be deterministic (otherwise RRF ranks — and the image gate — become flaky).
_DENSE_SQL = text(
    """
    SELECT id, source_type, source_id, content, metadata,
           1 - (embedding <=> CAST(:qvec AS vector)) AS score
    FROM chunks
    ORDER BY embedding <=> CAST(:qvec AS vector), id
    LIMIT :n
    """
)

_LEXICAL_SQL = text(
    """
    SELECT id, source_type, source_id, content, metadata,
           1 - (embedding <=> CAST(:qvec AS vector)) AS score,
           ts_rank_cd(tsv, plainto_tsquery('english', :q)) AS lex_rank
    FROM chunks
    WHERE tsv @@ plainto_tsquery('english', :q)
    ORDER BY lex_rank DESC, id
    LIMIT :n
    """
)


@dataclass
class RetrievedChunk:
    id: int
    source_type: str  # 'document' | 'image'
    source_id: int
    content: str
    metadata: dict[str, Any]
    score: float  # dense cosine similarity to the query (Gate 3 compares this)


def _to_chunk(row) -> RetrievedChunk:
    m = row._mapping
    return RetrievedChunk(
        id=m["id"],
        source_type=m["source_type"],
        source_id=m["source_id"],
        content=m["content"],
        metadata=m["metadata"] or {},
        score=float(m["score"]),
    )


def reciprocal_rank_fusion(
    dense: list[RetrievedChunk], lexical: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    """Rank-based fusion — no score normalization. Chunks keep their dense
    cosine `score`; the RRF value decides ordering only."""
    rrf_score: dict[int, float] = {}
    by_id: dict[int, RetrievedChunk] = {}
    for ranked_list in (dense, lexical):
        for rank, chunk in enumerate(ranked_list):
            rrf_score[chunk.id] = rrf_score.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            by_id.setdefault(chunk.id, chunk)
    ordered = sorted(rrf_score, key=lambda chunk_id: rrf_score[chunk_id], reverse=True)
    return [by_id[chunk_id] for chunk_id in ordered]


def retrieve(query: str, k: int | None = None) -> list[RetrievedChunk]:
    if k is None:
        k = settings.RETRIEVAL_TOP_K
    query_vector = embeddings.embed(query)
    vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

    db = SessionLocal()
    try:
        dense = [
            _to_chunk(row)
            for row in db.execute(_DENSE_SQL, {"qvec": vector_literal, "n": k * 3})
        ]
        lexical = [
            _to_chunk(row)
            for row in db.execute(
                _LEXICAL_SQL, {"qvec": vector_literal, "q": query, "n": k * 3}
            )
        ]
    finally:
        db.close()

    return reciprocal_rank_fusion(dense, lexical)[:k]
