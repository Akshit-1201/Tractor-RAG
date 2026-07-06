"""Pure unit tests for the chat service: citation parsing, IDK detection, and
the four image-gate cases (spec §19 — the accuracy criterion)."""

from app.config import settings
from app.core.prompts import IDK_MESSAGE
from app.services import chat as chat_service
from app.services.chat import (
    is_idk,
    map_numbers_to_chunk_ids,
    parse_answer_and_citations,
    resolve_standalone,
    select_image,
)
from app.services.retrieval import RetrievedChunk


def _doc(chunk_id: int, score: float = 0.6) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        source_type="document",
        source_id=1,
        content="Text about tractor maintenance.",
        metadata={"source_name": "manual.pdf", "page": 1},
        score=score,
    )


def _img(chunk_id: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        source_type="image",
        source_id=5,
        content="A red battery warning light.",
        metadata={
            "image_url": f"/storage/images/img-{chunk_id}.png",
            "source_name": f"img-{chunk_id}.png",
        },
        score=score,
    )


# --- Citation parsing ---


def test_citation_parse():
    answer, numbers = parse_answer_and_citations("The light means a fault.\nCITED: [1, 3]")
    assert answer == "The light means a fault."
    assert numbers == [1, 3]

    answer, numbers = parse_answer_and_citations(f"{IDK_MESSAGE}\nCITED: []")
    assert answer == IDK_MESSAGE
    assert numbers == []


def test_citation_parse_without_cited_line_is_conservative():
    answer, numbers = parse_answer_and_citations("An answer with no trailer.")
    assert answer == "An answer with no trailer."
    assert numbers == []


def test_map_numbers_to_chunk_ids():
    chunks = [_doc(11), _doc(22), _img(33, 0.5)]
    assert map_numbers_to_chunk_ids([1, 3], chunks) == [11, 33]
    assert map_numbers_to_chunk_ids([2, 9], chunks) == [22]  # out-of-range dropped
    assert map_numbers_to_chunk_ids([], chunks) == []


# --- IDK detection (normalized, never strict equality) ---


def test_is_idk_variants():
    assert is_idk(IDK_MESSAGE)
    assert is_idk("I don’t have information about that in the available documents.")  # curly
    assert is_idk("  i don't have information about that in the available documents  ")
    assert is_idk(IDK_MESSAGE.rstrip("."))
    assert is_idk("I'm sorry, I don't have information about that in the available documents.")
    assert not is_idk("A flashing red battery light indicates a charging fault.")
    assert not is_idk("I don't have the part number, but the manual says to check the belt.")


# --- Follow-up query resolution (multi-turn) ---


def test_resolve_standalone_without_history_is_identity(monkeypatch):
    """No history → the raw question passes through, and condensation is never
    invoked (turn 1 carries zero added cost)."""

    def _forbid(*args, **kwargs):
        raise AssertionError("condense must not run without history")

    monkeypatch.setattr(chat_service.condense, "condense_query", _forbid)
    assert resolve_standalone("what fluid type?", None) == "what fluid type?"
    assert resolve_standalone("what fluid type?", []) == "what fluid type?"


def test_resolve_standalone_with_history_delegates_to_condense(monkeypatch):
    seen = {}

    def _fake(history, question):
        seen["history"] = history
        seen["question"] = question
        return "What type of transmission fluid should I use?"

    monkeypatch.setattr(chat_service.condense, "condense_query", _fake)
    history = [{"role": "user", "content": "How do I change the transmission fluid?"}]

    assert (
        resolve_standalone("what fluid type?", history)
        == "What type of transmission fluid should I use?"
    )
    assert seen == {"history": history, "question": "what fluid type?"}


# --- The four image-gate cases (spec §9.4, Appendix A) ---


def test_image_gate_happy_path(monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_SIMILARITY_THRESHOLD", 0.35)
    chunks = [_doc(1), _img(2, score=0.72)]

    image = select_image(chunks, cited_chunk_ids=[1, 2], is_answered=True)

    assert image == {"url": "/storage/images/img-2.png", "caption": "img-2.png"}


def test_image_gate_retrieved_not_used(monkeypatch):
    """The engine-oil edge case: a relevant-looking diagram was retrieved but the
    answer never cited it → no image (retrieved ≠ used)."""
    monkeypatch.setattr(settings, "IMAGE_SIMILARITY_THRESHOLD", 0.35)
    chunks = [_doc(1), _img(2, score=0.8)]

    assert select_image(chunks, cited_chunk_ids=[1], is_answered=True) is None


def test_image_gate_no_image_on_idk(monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_SIMILARITY_THRESHOLD", 0.35)
    chunks = [_doc(1), _img(2, score=0.9)]

    assert select_image(chunks, cited_chunk_ids=[2], is_answered=False) is None


def test_image_gate_below_threshold(monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_SIMILARITY_THRESHOLD", 0.35)
    chunks = [_doc(1), _img(2, score=0.2)]

    assert select_image(chunks, cited_chunk_ids=[1, 2], is_answered=True) is None


def test_image_gate_picks_highest_scoring_candidate(monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_SIMILARITY_THRESHOLD", 0.35)
    chunks = [_img(1, score=0.5), _img(2, score=0.7)]

    image = select_image(chunks, cited_chunk_ids=[1, 2], is_answered=True)

    assert image is not None and image["url"] == "/storage/images/img-2.png"
