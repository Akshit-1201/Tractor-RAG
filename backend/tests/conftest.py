"""Shared fixtures. DB-backed tests run against DATABASE_URL (the compose db);
they skip cleanly when no database is reachable, e.g. when running on the host:

    docker compose exec -T backend pytest -q
"""

import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from app.services import embeddings as embeddings_service
from app.services import vision as vision_service

FAKE_VECTOR = [0.001] * 1536

FAKE_VISION_FIELDS = {
    "description": "A red battery warning light glowing on a dark tractor dashboard.",
    "category": "warning_light",
    "structured_fields": {"colour": "red", "severity": "high"},
}


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("database not reachable — run inside docker compose")
    return engine


@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Tests hammer the API far faster than real traffic; the dedicated 429 tests
    re-enable the limiter explicitly."""
    from app.core.ratelimit import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture
def seeded_chunks(db_engine):
    """Self-contained corpus rows so chat tests never depend on previously
    uploaded content — a fresh, empty database must pass the whole suite."""
    from app.database import SessionLocal
    from app.models import Chunk, Document, Image

    db = SessionLocal()
    document = Document(
        filename="pytest-fixture-manual.pdf",
        file_path="/tmp/pytest-fixture-manual.pdf",
        status="indexed",
        chunk_count=2,
    )
    image = Image(
        filename="pytest-fixture-light.png",
        file_path="/tmp/pytest-fixture-light.png",
        image_url="/storage/images/pytest-fixture-light.png",
        description="A red battery warning light.",
        status="indexed",
    )
    db.add_all([document, image])
    db.commit()
    db.refresh(document)
    db.refresh(image)

    chunks = [
        Chunk(
            source_type="document",
            source_id=document.id,
            content="A flashing red battery light indicates a charging system fault.",
            embedding=FAKE_VECTOR,
            meta={"source_name": document.filename, "page": 1},
        ),
        Chunk(
            source_type="document",
            source_id=document.id,
            content="Change the engine oil every 250 hours using filter AL-120.",
            embedding=FAKE_VECTOR,
            meta={"source_name": document.filename, "page": 2},
        ),
        Chunk(
            source_type="image",
            source_id=image.id,
            content="A red battery warning light.",
            embedding=FAKE_VECTOR,
            meta={"image_url": image.image_url, "source_name": image.filename},
        ),
    ]
    db.add_all(chunks)
    db.commit()
    chunk_ids = [chunk.id for chunk in chunks]

    yield {"document_id": document.id, "image_id": image.id, "chunk_ids": chunk_ids}

    db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).delete(synchronize_session=False)
    db.query(Image).filter(Image.id == image.id).delete(synchronize_session=False)
    db.query(Document).filter(Document.id == document.id).delete(synchronize_session=False)
    db.commit()
    db.close()


@pytest.fixture
def mock_openai(monkeypatch):
    """Deterministic OpenAI stand-ins: no network, no cost, stable vectors."""
    monkeypatch.setattr(embeddings_service, "embed_batch", lambda texts: [FAKE_VECTOR for _ in texts])
    monkeypatch.setattr(embeddings_service, "embed", lambda text: FAKE_VECTOR)
    monkeypatch.setattr(vision_service, "describe_image", lambda path: dict(FAKE_VISION_FIELDS))
