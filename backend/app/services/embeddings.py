"""Embedding service (spec §5.3) — shared by the ingestion path now and the query path in Phase 3."""

from openai import OpenAI

from app.config import settings

_BATCH_SIZE = 100  # inputs per API request; our chunks are well under per-input token limits

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Lazy singleton so tests can run (and modules import) without an API key."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def embed(text: str) -> list[float]:
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        response = get_client().embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts[start : start + _BATCH_SIZE],
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors
