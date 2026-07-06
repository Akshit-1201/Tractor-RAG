"""Unit tests for query condensation (multi-turn follow-up understanding).

The rewrite must: skip the LLM entirely when there is no usable history, return
the model's standalone rewrite when there is, and fall back to the raw question
on empty output or any API error — a follow-up never breaks the answer.
"""

import pytest

from app.services import condense


def _fake_client(*, returns=None, raises=None):
    """Minimal stand-in for the OpenAI client's chat.completions.create."""

    class _Message:
        content = returns

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            if raises is not None:
                raise raises
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


def _forbid_client():
    raise AssertionError("condensation must not call the model when history is empty")


def test_no_history_returns_question_without_calling_model(monkeypatch):
    monkeypatch.setattr(condense, "get_client", _forbid_client)
    assert condense.condense_query([], "what fluid type?") == "what fluid type?"


def test_blank_history_content_is_treated_as_empty(monkeypatch):
    monkeypatch.setattr(condense, "get_client", _forbid_client)
    history = [{"role": "user", "content": "   "}, {"role": "assistant", "content": ""}]
    assert condense.condense_query(history, "what fluid type?") == "what fluid type?"


def test_followup_is_rewritten_to_standalone(monkeypatch):
    monkeypatch.setattr(
        condense,
        "get_client",
        lambda: _fake_client(returns="What type of transmission fluid should I use?"),
    )
    history = [
        {"role": "user", "content": "How do I change the transmission fluid?"},
        {"role": "assistant", "content": "Drain the housing, then refill..."},
    ]
    assert (
        condense.condense_query(history, "what fluid type?")
        == "What type of transmission fluid should I use?"
    )


@pytest.mark.parametrize("returns", ["", "   ", None])
def test_empty_model_output_falls_back_to_raw_question(monkeypatch, returns):
    monkeypatch.setattr(condense, "get_client", lambda: _fake_client(returns=returns))
    history = [{"role": "user", "content": "How do I change the transmission fluid?"}]
    assert condense.condense_query(history, "what fluid type?") == "what fluid type?"


def test_api_error_falls_back_to_raw_question(monkeypatch):
    monkeypatch.setattr(
        condense, "get_client", lambda: _fake_client(raises=RuntimeError("boom"))
    )
    history = [{"role": "user", "content": "How do I change the transmission fluid?"}]
    assert condense.condense_query(history, "what fluid type?") == "what fluid type?"
