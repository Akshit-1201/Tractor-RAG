from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    category: Optional[str] = None
    image_url: str
    description: Optional[str] = None
    uploaded_at: datetime
