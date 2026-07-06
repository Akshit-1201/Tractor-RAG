"""Vision service (spec §9.2): exactly one multimodal call per image, at upload only."""

import base64
import json
import os

from app.config import settings
from app.core.prompts import VISION_PROMPT
from app.services.embeddings import get_client

_MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def describe_image(file_path: str) -> dict:
    """One vision call -> {description, category, structured_fields}."""
    extension = os.path.splitext(file_path)[1].lower()
    mime = _MIME_BY_EXTENSION.get(extension, "image/png")
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    response = get_client().chat.completions.create(
        model=settings.VISION_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}"},
                    },
                ],
            }
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return {
        "description": data.get("description", ""),
        "category": data.get("category", "other"),
        "structured_fields": data.get("structured_fields", {}),
    }
