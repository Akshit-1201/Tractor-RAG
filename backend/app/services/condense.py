"""Query condensation for multi-turn follow-up understanding (chat spec, follow-up
mode).

Turns a context-dependent follow-up ("what fluid type?") into a standalone
question using recent history, so both retrieval and the grounded answer see a
fully-specified query. History is used ONLY to reformulate the question — it is
never passed to the grounded answer call and can never become a source, so the
grounding guarantee (invariant #1) is untouched. Any failure, or an empty
history, falls back to the raw question: a follow-up degrades to today's
behaviour rather than breaking.
"""

import logging

from app.config import settings
from app.core.prompts import CONDENSE_PROMPT
from app.services.embeddings import get_client

logger = logging.getLogger(__name__)

_ROLE_LABELS = {"user": "Customer", "assistant": "Assistant"}
_MAX_ANSWER_CHARS = 500  # only the gist of a prior answer is needed to resolve a reference


def _format_history(history: list[dict]) -> str:
    """Render the recent turns as a compact transcript for the rewrite prompt."""
    lines: list[str] = []
    for turn in history:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant" and len(content) > _MAX_ANSWER_CHARS:
            content = content[:_MAX_ANSWER_CHARS] + "…"
        lines.append(f"{_ROLE_LABELS.get(role, 'Customer')}: {content}")
    return "\n".join(lines)


def condense_query(history: list[dict], question: str) -> str:
    """Reformulate ``question`` as a standalone query using ``history``.

    Returns the raw ``question`` unchanged when there is no usable history, when
    the model returns nothing, or on any API error.
    """
    formatted = _format_history(history)
    if not formatted:
        return question
    try:
        response = get_client().chat.completions.create(
            model=settings.CHAT_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": CONDENSE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Conversation so far:\n{formatted}\n\n"
                        f"Latest question: {question}\n\n"
                        "Standalone question:"
                    ),
                },
            ],
        )
        rewritten = (response.choices[0].message.content or "").strip()
        return rewritten or question
    except Exception:
        logger.exception("query condensation failed; using the raw question")
        return question
