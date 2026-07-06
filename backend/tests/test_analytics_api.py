"""GET /api/admin/analytics: guard, shape, computation, and the empty-table zero case."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.main import app
from app.services.analytics import get_stats

_ALL_COLUMNS = (
    "id, question_text, answer_text, is_answered, retrieved_chunk_ids,"
    " cited_chunk_ids, image_shown, topic, latency_ms, created_at"
)


@pytest.fixture(autouse=True)
def _clean_questions(db_engine):
    yield
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM questions WHERE question_text LIKE 'pytest-%'"))


def _login_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/admin/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _insert_question(conn, text_value: str, is_answered: bool, topic: str) -> None:
    conn.execute(
        text(
            "INSERT INTO questions (question_text, answer_text, is_answered, topic)"
            " VALUES (:q, 'answer', :a, :t)"
        ),
        {"q": text_value, "a": is_answered, "t": topic},
    )


def test_analytics_endpoint_shape(db_engine):
    client = TestClient(app)
    assert client.get("/api/admin/analytics").status_code == 401

    response = client.get("/api/admin/analytics", headers=_login_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "total_questions",
        "answered",
        "unknown",
        "answer_rate",
        "top_topics",
        "recent_questions",
    }


def test_analytics_computation(db_engine):
    client = TestClient(app)
    headers = _login_headers(client)
    before = client.get("/api/admin/analytics", headers=headers).json()

    with db_engine.begin() as conn:
        _insert_question(conn, "pytest-q1", True, "pytest-topic")
        _insert_question(conn, "pytest-q2", True, "pytest-topic")
        _insert_question(conn, "pytest-q3", True, "pytest-topic")
        _insert_question(conn, "pytest-q4-newest", False, "pytest-topic")

    body = client.get("/api/admin/analytics", headers=headers).json()

    assert body["total_questions"] == before["total_questions"] + 4
    assert body["answered"] == before["answered"] + 3
    assert body["unknown"] == before["unknown"] + 1
    assert body["answered"] + body["unknown"] == body["total_questions"]
    assert body["answer_rate"] == round(body["answered"] / body["total_questions"], 3)

    # topic check via get_stats with a wide top_n: the endpoint's top-5 can be
    # crowded out once real demo traffic accumulates — this stays deterministic
    topic_counts = {t["topic"]: t["count"] for t in get_stats(top_n=1000)["top_topics"]}
    assert topic_counts.get("pytest-topic") == 4

    assert body["recent_questions"][0]["question"] == "pytest-q4-newest"
    assert body["recent_questions"][0]["is_answered"] is False


def test_analytics_empty_table_returns_zeros(db_engine):
    client = TestClient(app)
    headers = _login_headers(client)

    with db_engine.connect() as conn:
        snapshot = [dict(row) for row in conn.execute(
            text(f"SELECT {_ALL_COLUMNS} FROM questions")
        ).mappings()]

    try:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM questions"))

        body = client.get("/api/admin/analytics", headers=headers).json()

        assert body["total_questions"] == 0
        assert body["answered"] == 0 and body["unknown"] == 0
        assert body["answer_rate"] == 0.0
        assert body["top_topics"] == [] and body["recent_questions"] == []
    finally:
        if snapshot:
            with db_engine.begin() as conn:
                conn.execute(
                    text(
                        f"INSERT INTO questions ({_ALL_COLUMNS}) VALUES"
                        " (:id, :question_text, :answer_text, :is_answered,"
                        "  :retrieved_chunk_ids, :cited_chunk_ids, :image_shown,"
                        "  :topic, :latency_ms, :created_at)"
                    ),
                    snapshot,
                )
