from app.services.retrieval import RetrievedChunk, reciprocal_rank_fusion


def _chunk(chunk_id: int, score: float = 0.5, content: str = "text") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        source_type="document",
        source_id=1,
        content=content,
        metadata={"source_name": f"src-{chunk_id}"},
        score=score,
    )


def test_rrf_fusion_agreement_wins():
    """A chunk ranked by BOTH signals must outrank single-signal leaders."""
    both = _chunk(1, score=0.61)
    dense_only = _chunk(2)
    lexical_only = _chunk(3)

    fused = reciprocal_rank_fusion([dense_only, both], [both, lexical_only])

    assert fused[0].id == 1


def test_rrf_rescues_lexical_only_code_match():
    """An exact code match (E-047) found only by lexical search must reach the top-k."""
    dense = [_chunk(i) for i in range(1, 25)]  # k*3 dense results, no code match
    code_chunk = _chunk(99, score=0.12, content="Error code E-047: fuel injector circuit fault")

    fused = reciprocal_rank_fusion(dense, [code_chunk])[:8]

    assert any(c.id == 99 for c in fused)


def test_rrf_preserves_dense_cosine_scores():
    """Fusion must never overwrite `score` with the ~0.03-scale RRF value (Gate 3
    depends on the dense cosine similarity — spec §8.3)."""
    a, b = _chunk(1, score=0.72), _chunk(2, score=0.4)

    fused = reciprocal_rank_fusion([a, b], [b, a])

    assert {c.id: c.score for c in fused} == {1: 0.72, 2: 0.4}
    assert all(c.score > 0.1 for c in fused)
