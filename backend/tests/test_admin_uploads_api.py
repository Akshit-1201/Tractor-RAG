import io

import fitz
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config import settings
from app.main import app
from app.routers.admin import _save_upload


def _pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _login_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_upload_requires_token(db_engine):
    client = TestClient(app)
    response = client.post(
        "/api/admin/documents",
        files={"file": ("manual.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_rejects_non_pdf(db_engine):
    client = TestClient(app)
    response = client.post(
        "/api/admin/documents",
        headers=_login_headers(client),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_upload_rejects_bad_image_type(db_engine):
    client = TestClient(app)
    response = client.post(
        "/api/admin/images",
        headers=_login_headers(client),
        files={"file": ("clip.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 415


def test_upload_document_202_then_indexed_then_deleted(db_engine, mock_openai):
    client = TestClient(app)
    headers = _login_headers(client)

    response = client.post(
        "/api/admin/documents",
        headers=headers,
        files={
            "file": (
                "pytest-api.pdf",
                _pdf_bytes("Coolant level must be checked before each shift."),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["filename"] == "pytest-api.pdf"
    assert body["status"] == "processing"

    # TestClient runs the background task before returning, so the list reflects it
    listed = client.get("/api/admin/documents", headers=headers).json()
    mine = next(d for d in listed if d["id"] == body["id"])
    assert mine["status"] == "indexed"
    assert mine["chunk_count"] > 0

    assert client.delete(f"/api/admin/documents/{body['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/admin/documents/{body['id']}", headers=headers).status_code == 404


def test_upload_too_large_413(db_engine, monkeypatch):
    client = TestClient(app)
    headers = _login_headers(client)  # before shrinking the limit
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)

    oversized = b"%PDF-1.4 " + b"0" * (2 * 1024 * 1024)  # over limit + 1 MB middleware slack
    response = client.post(
        "/api/admin/documents",
        headers=headers,
        files={"file": ("pytest-huge.pdf", oversized, "application/pdf")},
    )
    assert response.status_code == 413

    listed = client.get("/api/admin/documents", headers=headers).json()
    assert all(d["filename"] != "pytest-huge.pdf" for d in listed)


def test_save_upload_stream_cap_cleans_partial(monkeypatch, tmp_path):
    """The exact per-file stream check: 413 plus removal of the partial file."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)
    monkeypatch.setattr(settings, "STORAGE_PATH", str(tmp_path))
    upload = StarletteUploadFile(file=io.BytesIO(b"x" * 2048), filename="pytest-cap.pdf")

    with pytest.raises(HTTPException) as exc_info:
        _save_upload(upload, "documents")

    assert exc_info.value.status_code == 413
    assert list((tmp_path / "documents").glob("*pytest-cap.pdf")) == []
