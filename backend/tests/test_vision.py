import json

from app.config import settings
from app.services import vision


def test_vision_service_parses_json(monkeypatch, tmp_path):
    payload = {
        "description": "A red battery warning light.",
        "category": "warning_light",
        "structured_fields": {"colour": "red"},
    }
    seen: dict = {}

    class _Completions:
        def create(self, **kwargs):
            seen.update(kwargs)

            class _Message:
                content = json.dumps(payload)

            class _Choice:
                message = _Message()

            class _Response:
                choices = [_Choice()]

            return _Response()

    class _Client:
        class chat:
            completions = _Completions()

    monkeypatch.setattr(vision, "get_client", lambda: _Client())

    image_path = tmp_path / "light.png"
    image_path.write_bytes(b"\x89PNG-fake-bytes")

    result = vision.describe_image(str(image_path))

    assert result == payload
    assert seen["model"] == settings.VISION_MODEL
    assert seen["response_format"] == {"type": "json_object"}
    image_part = seen["messages"][0]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_vision_fills_missing_fields(monkeypatch, tmp_path):
    class _Completions:
        def create(self, **kwargs):
            class _Message:
                content = json.dumps({"description": "A diagram."})

            class _Choice:
                message = _Message()

            class _Response:
                choices = [_Choice()]

            return _Response()

    class _Client:
        class chat:
            completions = _Completions()

    monkeypatch.setattr(vision, "get_client", lambda: _Client())
    image_path = tmp_path / "diagram.jpg"
    image_path.write_bytes(b"fake")

    result = vision.describe_image(str(image_path))

    assert result["category"] == "other"
    assert result["structured_fields"] == {}
