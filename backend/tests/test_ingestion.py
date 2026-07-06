import fitz
from sqlalchemy import text

from app.database import SessionLocal
from app.models import Chunk, Document, Image
from app.services import ingestion


def _make_pdf(path: str, pages_text: list[str]) -> None:
    doc = fitz.open()
    for page_text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), page_text)
    doc.save(path)
    doc.close()


def _document_chunks(db, document_id: int) -> list[Chunk]:
    return (
        db.query(Chunk)
        .filter(Chunk.source_type == "document", Chunk.source_id == document_id)
        .all()
    )


def test_ingest_document_integration(db_engine, mock_openai, tmp_path):
    pdf_path = str(tmp_path / "manual.pdf")
    _make_pdf(
        pdf_path,
        [
            "A flashing red battery light indicates a charging system fault. "
            "Stop the engine and inspect the alternator belt.",
            "Change the engine oil every 250 hours. Use filter part AL-120.",
        ],
    )
    db = SessionLocal()
    document = Document(filename="pytest-manual.pdf", file_path=pdf_path, status="processing")
    db.add(document)
    db.commit()
    db.refresh(document)
    try:
        ingestion.ingest_document(document.id)

        db.refresh(document)
        assert document.status == "indexed"
        assert document.chunk_count > 0

        chunks = _document_chunks(db, document.id)
        assert len(chunks) == document.chunk_count
        assert all(c.embedding is not None for c in chunks)
        assert chunks[0].meta["source_name"] == "pytest-manual.pdf"
        assert chunks[0].meta["page"] >= 1

        with db_engine.connect() as conn:
            tsv_nulls = conn.execute(
                text(
                    "SELECT count(*) FROM chunks "
                    "WHERE source_type = 'document' AND source_id = :i AND tsv IS NULL"
                ),
                {"i": document.id},
            ).scalar()
        assert tsv_nulls == 0, "tsv trigger did not populate ingested chunks"
    finally:
        db.refresh(document)
        ingestion.delete_document(db, document)
        db.close()


def test_ingest_document_failure_marks_failed(db_engine, mock_openai):
    db = SessionLocal()
    document = Document(
        filename="pytest-missing.pdf", file_path="/nonexistent/nowhere.pdf", status="processing"
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    try:
        ingestion.ingest_document(document.id)

        db.refresh(document)
        assert document.status == "failed"
        assert _document_chunks(db, document.id) == []
    finally:
        db.refresh(document)
        ingestion.delete_document(db, document)
        db.close()


def test_delete_document_removes_chunks(db_engine, mock_openai, tmp_path):
    pdf_path = str(tmp_path / "todelete.pdf")
    _make_pdf(pdf_path, ["Grease the front axle bearings every 50 hours."])
    db = SessionLocal()
    document = Document(filename="pytest-delete.pdf", file_path=pdf_path, status="processing")
    db.add(document)
    db.commit()
    db.refresh(document)
    document_id = document.id
    try:
        ingestion.ingest_document(document_id)
        db.refresh(document)
        assert _document_chunks(db, document_id), "precondition: chunks exist"

        ingestion.delete_document(db, document)

        assert _document_chunks(db, document_id) == []
        assert db.get(Document, document_id) is None
    finally:
        db.close()


def test_ingest_image_integration(db_engine, mock_openai, tmp_path):
    image_path = tmp_path / "light.png"
    image_path.write_bytes(b"\x89PNG-fake")  # vision is mocked; bytes are never decoded
    db = SessionLocal()
    image = Image(
        filename="pytest-light.png",
        file_path=str(image_path),
        image_url="/storage/images/pytest-light.png",
        status="processing",
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    try:
        ingestion.ingest_image(image.id)

        db.refresh(image)
        assert image.status == "indexed"
        assert image.description
        assert image.category == "warning_light"
        assert image.structured_fields["colour"] == "red"

        chunks = (
            db.query(Chunk)
            .filter(Chunk.source_type == "image", Chunk.source_id == image.id)
            .all()
        )
        assert len(chunks) == 1
        assert chunks[0].content == image.description
        assert chunks[0].meta["image_url"] == "/storage/images/pytest-light.png"
        assert chunks[0].meta["source_name"] == "pytest-light.png"
    finally:
        db.refresh(image)
        ingestion.delete_image(db, image)
        db.close()


def test_delete_image_removes_chunk(db_engine, mock_openai, tmp_path):
    image_path = tmp_path / "gone.png"
    image_path.write_bytes(b"fake")
    db = SessionLocal()
    image = Image(
        filename="pytest-gone.png",
        file_path=str(image_path),
        image_url="/storage/images/pytest-gone.png",
        status="processing",
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    image_id = image.id
    try:
        ingestion.ingest_image(image_id)
        db.refresh(image)

        ingestion.delete_image(db, image)

        remaining = (
            db.query(Chunk)
            .filter(Chunk.source_type == "image", Chunk.source_id == image_id)
            .count()
        )
        assert remaining == 0
        assert db.get(Image, image_id) is None
        assert not image_path.exists()
    finally:
        db.close()
