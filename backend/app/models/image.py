from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # on-disk path
    image_url: Mapped[str] = mapped_column(Text, nullable=False)  # URL served to the frontend
    description: Mapped[Optional[str]] = mapped_column(Text)  # vision-generated caption
    # warning_light | parts_diagram | engine_layout | other
    category: Mapped[Optional[str]] = mapped_column(Text)
    structured_fields: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'processing'"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
