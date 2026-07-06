"""Ingestion service (spec §8.1, §9.2): the expensive upload path.

Runs as FastAPI background tasks — each function opens its own session, flips the
row's status to 'indexed' on success or 'failed' on any error, and never raises.
Deletes cascade to chunks in this layer (global constraint: the index must always
mirror what the admin has uploaded).
"""

import logging
import os

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Chunk, Document, Image
from app.services import embeddings, vision
from app.utils.chunking import chunk_pages
from app.utils.pdf_parser import extract_pages

logger = logging.getLogger(__name__)


def ingest_document(document_id: int) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return
        try:
            pages = extract_pages(document.file_path)
            chunks = chunk_pages(
                pages,
                source_name=document.filename,
                target_tokens=settings.CHUNK_TARGET_TOKENS,
                overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
            )
            if not chunks:
                raise ValueError("no extractable text (scanned/empty PDF?)")
            vectors = embeddings.embed_batch([c["content"] for c in chunks])
            for chunk, vector in zip(chunks, vectors):
                db.add(
                    Chunk(
                        source_type="document",
                        source_id=document.id,
                        content=chunk["content"],
                        embedding=vector,
                        meta=chunk["metadata"],
                    )
                )
            document.status = "indexed"
            document.chunk_count = len(chunks)
            db.commit()
        except Exception:
            logger.exception("document ingestion failed (id=%s)", document_id)
            db.rollback()
            document.status = "failed"
            db.commit()
    finally:
        db.close()


def ingest_image(image_id: int) -> None:
    db = SessionLocal()
    try:
        image = db.get(Image, image_id)
        if image is None:
            return
        try:
            fields = vision.describe_image(image.file_path)  # the one vision call
            if not fields["description"]:
                raise ValueError("vision returned an empty description")
            image.description = fields["description"]
            image.category = fields["category"]
            image.structured_fields = fields["structured_fields"]
            db.add(
                Chunk(
                    source_type="image",
                    source_id=image.id,
                    content=image.description,
                    embedding=embeddings.embed(image.description),
                    meta={"image_url": image.image_url, "source_name": image.filename},
                )
            )
            image.status = "indexed"
            db.commit()
        except Exception:
            logger.exception("image ingestion failed (id=%s)", image_id)
            db.rollback()
            image.status = "failed"
            db.commit()
    finally:
        db.close()


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def delete_document(db: Session, document: Document) -> None:
    db.query(Chunk).filter(
        Chunk.source_type == "document", Chunk.source_id == document.id
    ).delete()
    _remove_file(document.file_path)
    db.delete(document)
    db.commit()


def delete_image(db: Session, image: Image) -> None:
    db.query(Chunk).filter(Chunk.source_type == "image", Chunk.source_id == image.id).delete()
    _remove_file(image.file_path)
    db.delete(image)
    db.commit()
