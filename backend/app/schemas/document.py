from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadAccepted(BaseModel):
    """202 body for both document and image uploads (spec §10.2/§10.3)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    chunk_count: int
    uploaded_at: datetime
