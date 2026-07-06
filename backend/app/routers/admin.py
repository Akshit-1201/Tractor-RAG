"""Admin router (/api/admin/*, spec §10.1–§10.3). Thin: validation only — pipeline
logic lives in the ingestion service. Every route except login is JWT-guarded.
"""

import os
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.core.ratelimit import limiter
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.dependencies import get_current_admin
from app.models import Admin, Document, Image
from app.schemas.analytics import AnalyticsResponse
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.document import DocumentOut, UploadAccepted
from app.schemas.image import ImageOut
from app.services import analytics, ingestion

router = APIRouter()

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)  # brute-force guard (spec §15)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    admin = db.query(Admin).filter(Admin.username == body.username).first()
    if admin is None or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenResponse(access_token=create_access_token(admin.username))


def _save_upload(file: UploadFile, subdir: str) -> tuple[str, str]:
    """Stream to STORAGE_PATH/<subdir>/ under a unique name, enforcing MAX_UPLOAD_MB.

    Returns (disk_path, stored_name).
    """
    safe_name = os.path.basename(file.filename or "upload")
    stored_name = f"{uuid4().hex[:8]}_{safe_name}"
    directory = os.path.join(settings.STORAGE_PATH, subdir)
    os.makedirs(directory, exist_ok=True)
    disk_path = os.path.join(directory, stored_name)

    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    too_big = False
    with open(disk_path, "wb") as out:
        while block := file.file.read(1024 * 1024):
            size += len(block)
            if size > limit:
                too_big = True
                break
            out.write(block)
    if too_big:
        os.remove(disk_path)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit",
        )
    return disk_path, stored_name


# --- Documents (spec §10.2) ---


@router.post(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAccepted,
    dependencies=[Depends(get_current_admin)],
)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    is_pdf = file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF documents are accepted")
    disk_path, _ = _save_upload(file, "documents")
    document = Document(filename=file.filename, file_path=disk_path, status="processing")
    db.add(document)
    db.commit()
    db.refresh(document)
    background_tasks.add_task(ingestion.ingest_document, document.id)
    return document


@router.get(
    "/documents",
    response_model=list[DocumentOut],
    dependencies=[Depends(get_current_admin)],
)
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.uploaded_at.desc()).all()


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
def delete_document(document_id: int, db: Session = Depends(get_db)) -> Response:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    ingestion.delete_document(db, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Images (spec §10.3) ---


@router.post(
    "/images",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAccepted,
    dependencies=[Depends(get_current_admin)],
)
def upload_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Image:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only PNG, JPEG, or WebP images are accepted",
        )
    disk_path, stored_name = _save_upload(file, "images")
    image = Image(
        filename=file.filename,
        file_path=disk_path,
        image_url=f"/storage/images/{stored_name}",
        status="processing",
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    background_tasks.add_task(ingestion.ingest_image, image.id)
    return image


@router.get(
    "/images",
    response_model=list[ImageOut],
    dependencies=[Depends(get_current_admin)],
)
def list_images(db: Session = Depends(get_db)) -> list[Image]:
    return db.query(Image).order_by(Image.uploaded_at.desc()).all()


@router.delete(
    "/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
def delete_image(image_id: int, db: Session = Depends(get_db)) -> Response:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    ingestion.delete_image(db, image)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Analytics (spec §10.4) ---


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    dependencies=[Depends(get_current_admin)],
)
def get_analytics() -> dict:
    return analytics.get_stats()
