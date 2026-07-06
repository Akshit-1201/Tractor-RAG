"""DB-backed chat orchestration tests: the grounding refusal and analytics
logging, running real retrieval against the seeded corpus with a mocked LLM."""

import pytest
from sqlalchemy import text

from app.core.prompts import IDK_MESSAGE
from app.services import chat as chat_service


@pytest.fixture(autouse=True)
def _clean_questions(db_engine):
    yield
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM questions WHERE question_text LIKE 'pytest-%'"))


def test_grounding_refusal(db_engine, mock_openai, monkeypatch):
    """Appendix A.4: out-of-scope question → exactly the IDK string, no sources, no image."""
    monkeypatch.setattr(
        chat_service, "_llm_answer", lambda context, query: f"{IDK_MESSAGE}\nCITED: []"
    )

    result = chat_service.answer_question("pytest-a4 What's the best fertilizer for wheat?")

    assert result.answer == IDK_MESSAGE  # exact string, verbatim
    assert result.is_answered is False
    assert result.sources == []
    assert result.image is None


def test_idk_with_citations_still_carries_nothing(db_engine, mock_openai, monkeypatch):
    """Even if the model emits IDK *and* citations, the system-level gate forces
    empty sources and no image (spec §8.5)."""
    monkeypatch.setattr(
        chat_service, "_llm_answer", lambda context, query: f"{IDK_MESSAGE}\nCITED: [1, 2]"
    )

    result = chat_service.answer_question("pytest-idk-cited nonsense question")

    assert result.is_answered is False
    assert result.sources == []
    assert result.image is None


def test_answer_logs_question(db_engine, mock_openai, seeded_chunks, monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "_llm_answer",
        lambda context, query: "Change the oil every 250 hours using filter AL-120.\nCITED: [1]",
    )
    question = "pytest-log How often should I change the engine oil filter?"

    result = chat_service.answer_question(question)

    assert result.is_answered is True
    with db_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT is_answered, retrieved_chunk_ids, cited_chunk_ids,"
                "       image_shown, topic, latency_ms"
                "  FROM questions WHERE question_text = :q"
            ),
            {"q": question},
        ).one()
    assert row.is_answered is True
    assert len(row.retrieved_chunk_ids) > 0
    assert len(row.cited_chunk_ids) == 1
    assert row.image_shown is False
    assert row.topic is not None
    assert row.latency_ms is not None


def test_idk_logged_as_unanswered(db_engine, mock_openai, monkeypatch):
    monkeypatch.setattr(
        chat_service, "_llm_answer", lambda context, query: f"{IDK_MESSAGE}\nCITED: []"
    )
    question = "pytest-unanswered something out of scope"

    chat_service.answer_question(question)

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT is_answered, cited_chunk_ids FROM questions WHERE question_text = :q"),
            {"q": question},
        ).one()
    assert row.is_answered is False
    assert row.cited_chunk_ids == []


def test_empty_model_output_becomes_idk(db_engine, mock_openai, monkeypatch):
    """A blank model response must never present as a confident answer."""
    monkeypatch.setattr(chat_service, "_llm_answer", lambda context, query: "")

    result = chat_service.answer_question("pytest-empty model output")

    assert result.answer == IDK_MESSAGE
    assert result.is_answered is False
    assert result.sources == [] and result.image is None


# --- Multi-turn follow-up understanding ---


def test_followup_condenses_before_retrieval_and_grounds(
    db_engine, mock_openai, seeded_chunks, monkeypatch
):
    """A follow-up is rewritten to a standalone query, which then drives retrieval
    and the grounded answer. The rewritten query — not the raw follow-up — is what
    reaches the answer call."""
    seen = {}

    def _spy_condense(history, question):
        seen["history"] = history
        return "How often should I change the engine oil filter?"

    def _answer(context, query):
        seen["answer_query"] = query
        return "Change the oil filter every 250 hours.\nCITED: [1]"

    monkeypatch.setattr(chat_service.condense, "condense_query", _spy_condense)
    monkeypatch.setattr(chat_service, "_llm_answer", _answer)

    history = [{"role": "user", "content": "pytest-mt How do I service the engine?"}]
    result = chat_service.answer_question("pytest-mt what about the filter?", history)

    assert seen["history"] == history
    assert seen["answer_query"] == "How often should I change the engine oil filter?"
    assert result.is_answered is True


def test_grounding_preserved_on_followup(db_engine, mock_openai, seeded_chunks, monkeypatch):
    """History can never manufacture grounding: an off-domain follow-up still
    resolves to the canonical IDK, with no sources and no image."""
    monkeypatch.setattr(
        chat_service.condense,
        "condense_query",
        lambda history, question: "What is the best fertilizer for wheat?",
    )
    monkeypatch.setattr(
        chat_service, "_llm_answer", lambda context, query: f"{IDK_MESSAGE}\nCITED: []"
    )

    history = [{"role": "user", "content": "pytest-mt tell me about crops"}]
    result = chat_service.answer_question("pytest-mt and the best one?", history)

    assert result.answer == IDK_MESSAGE
    assert result.is_answered is False
    assert result.sources == [] and result.image is None
