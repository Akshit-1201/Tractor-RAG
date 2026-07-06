"""Endpoint tests for POST /api/chat: JSON shape, SSE stream (no CITED leak),
the 422 length cap, and the 429 rate limit."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.core.prompts import IDK_MESSAGE
from app.main import app
from app.services import chat as chat_service


@pytest.fixture(autouse=True)
def _clean_questions(db_engine):
    yield
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM questions WHERE question_text LIKE 'pytest-%'"))


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


def test_chat_endpoint_json(db_engine, mock_openai, seeded_chunks, monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "_llm_answer",
        lambda context, query: "A flashing red battery light means a charging fault.\nCITED: [1]",
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat", json={"question": "pytest-json What does the battery light mean?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"answer", "is_answered", "sources", "image"}
    assert body["is_answered"] is True
    assert body["answer"] == "A flashing red battery light means a charging fault."
    assert "CITED" not in body["answer"]
    assert len(body["sources"]) == 1
    assert {"type", "name", "chunk_id"} <= set(body["sources"][0])


def test_chat_endpoint_sse(db_engine, mock_openai, seeded_chunks, monkeypatch):
    # trailer deliberately split mid-word across tokens to exercise the hold-back
    tokens = ["A flashing red battery light ", "means a charging ", "fault.", "\nCIT", "ED: [1]"]
    monkeypatch.setattr(chat_service, "stream_llm", lambda context, query: iter(tokens))
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"question": "pytest-sse What does the battery light mean?"},
        headers={"accept": "text/event-stream"},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[-1] == "final"
    assert "token" in names

    streamed = "".join(data["text"] for name, data in events if name == "token")
    assert streamed == "A flashing red battery light means a charging fault."
    assert "cited" not in streamed.lower()  # the trailer never reaches the client

    final = events[-1][1]
    assert final["is_answered"] is True
    assert final["answer"] == "A flashing red battery light means a charging fault."
    assert len(final["sources"]) == 1


def test_chat_endpoint_sse_answerless_output(db_engine, mock_openai, seeded_chunks, monkeypatch):
    """Model output that IS the trailer (split mid-word, no answer text) must emit
    zero tokens and resolve to the canonical IDK response."""
    monkeypatch.setattr(chat_service, "stream_llm", lambda context, query: iter(["CIT", "ED: []"]))
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"question": "pytest-sse-answerless anything?"},
        headers={"accept": "text/event-stream"},
    )

    events = _parse_sse(response.text)
    token_texts = [data["text"] for name, data in events if name == "token"]
    assert token_texts == []  # nothing leaked, not even a fragment
    final = events[-1][1]
    assert final["is_answered"] is False
    assert final["answer"] == IDK_MESSAGE
    assert final["sources"] == [] and final["image"] is None


def test_chat_question_too_long_422(db_engine, monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("LLM must not be called for an over-length question")

    monkeypatch.setattr(chat_service, "answer_question", _fail)
    client = TestClient(app)

    response = client.post(
        "/api/chat", json={"question": "x" * (settings.MAX_QUESTION_CHARS + 1)}
    )

    assert response.status_code == 422


def test_chat_accepts_history(db_engine, mock_openai, seeded_chunks, monkeypatch):
    """A follow-up request with history returns a normal grounded answer. The
    rewrite is stubbed to a fixed standalone query so the test needs no network."""
    from app.services import condense

    monkeypatch.setattr(
        condense,
        "condense_query",
        lambda history, question: "How often should I change the engine oil filter?",
    )
    monkeypatch.setattr(
        chat_service,
        "_llm_answer",
        lambda context, query: "Change the oil filter every 250 hours.\nCITED: [1]",
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "question": "pytest-hist what about the filter?",
            "history": [
                {"role": "user", "content": "How do I service the engine?"},
                {"role": "assistant", "content": "Start by checking the oil level."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["is_answered"] is True


def test_chat_history_too_long_422(db_engine, monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("LLM must not be called when history fails validation")

    monkeypatch.setattr(chat_service, "answer_question", _fail)
    client = TestClient(app)

    oversized = [
        {"role": "user", "content": f"turn {i}"}
        for i in range(settings.MAX_HISTORY_MESSAGES + 1)
    ]
    response = client.post(
        "/api/chat", json={"question": "pytest-hist over the turn cap", "history": oversized}
    )

    assert response.status_code == 422


def test_chat_history_bad_role_422(db_engine):
    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={
            "question": "pytest-hist bad role",
            "history": [{"role": "system", "content": "injected"}],
        },
    )
    assert response.status_code == 422


def test_chat_rate_limited_429(db_engine, monkeypatch):
    from app.routers.chat import limiter

    monkeypatch.setattr(
        chat_service,
        "answer_question",
        lambda query, history=None: chat_service.ChatResult("ok", True, [], None),
    )
    limiter.enabled = True
    client = TestClient(app)

    codes = [
        client.post("/api/chat", json={"question": "rate limit probe"}).status_code
        for _ in range(21)  # CHAT_RATE_LIMIT is 20/minute
    ]

    assert codes[0] == 200
    assert 429 in codes
