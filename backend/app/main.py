import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.ratelimit import limiter
from app.routers import admin, chat

app = FastAPI(title="Tractor Maintenance Assistant")

# Per-IP rate limiting (spec §15): public chat + admin login
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_UPLOAD_PATHS = {"/api/admin/documents", "/api/admin/images"}


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Cheap early 413 from the Content-Length header, before the multipart body
    is parsed. 1 MB of slack covers multipart overhead — the per-file stream
    check in the admin router remains the exact enforcement.
    """
    if request.method == "POST" and request.url.path in _UPLOAD_PATHS:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > (settings.MAX_UPLOAD_MB + 1) * 1024 * 1024:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Upload exceeds the {settings.MAX_UPLOAD_MB} MB limit"},
            )
    return await call_next(request)


# Added after the upload guard so CORS runs outermost and its headers apply to 413s too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(chat.router, prefix="/api", tags=["chat"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Only reference images are public — the customer chat renders them (spec §9.3).
# Raw uploaded PDFs under STORAGE_PATH/documents are deliberately NOT served.
_images_dir = os.path.join(settings.STORAGE_PATH, "images")
os.makedirs(_images_dir, exist_ok=True)
app.mount("/storage/images", StaticFiles(directory=_images_dir), name="storage-images")
