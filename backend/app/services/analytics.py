"""Analytics service (spec §13): log every customer question; compute usage stats."""

import logging
from typing import Optional

from sqlalchemy import func

from app.database import SessionLocal
from app.models import Question

logger = logging.getLogger(__name__)

# Ordered: first match wins, so the more specific topics come first.
_TOPIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("warning lights", ["warning light", "battery light", "dashboard light", "indicator", "light mean", "light on"]),
    ("error codes", ["error code", "fault code", "code e-", "e-0"]),
    ("transmission", ["transmission", "gearbox", "clutch"]),
    ("hydraulics", ["hydraulic", "loader", "three-point", "hitch"]),
    ("brakes", ["brake", "pedal"]),
    ("engine", ["engine", "oil", "injector", "coolant", "overheat", "alternator", "fuel"]),
    ("maintenance schedule", ["schedule", "interval", "hours", "service", "filter", "grease"]),
]


def classify_topic(query: str) -> str:
    """Cheap keyword classification at log time; 'other' keeps top_topics NULL-free."""
    lowered = query.lower()
    for topic, keywords in _TOPIC_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return topic
    return "other"


def log(
    query: str,
    answer_text: str,
    is_answered: bool,
    retrieved: list[int],
    cited: list[int],
    image_shown: bool,
    latency_ms: Optional[int] = None,
) -> None:
    """Insert one questions row. Never lets an analytics failure break the answer."""
    try:
        db = SessionLocal()
        try:
            db.add(
                Question(
                    question_text=query,
                    answer_text=answer_text,
                    is_answered=is_answered,
                    retrieved_chunk_ids=retrieved,
                    cited_chunk_ids=cited,
                    image_shown=image_shown,
                    topic=classify_topic(query),
                    latency_ms=latency_ms,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception("failed to log question for analytics")


def get_stats(top_n: int = 5, recent_n: int = 10) -> dict:
    """Usage statistics for the admin dashboard (spec §10.4, §13)."""
    db = SessionLocal()
    try:
        total = db.query(func.count(Question.id)).scalar() or 0
        answered = (
            db.query(func.count(Question.id)).filter(Question.is_answered.is_(True)).scalar() or 0
        )
        unknown = total - answered
        answer_rate = round(answered / total, 3) if total else 0.0  # guard divide-by-zero

        topic_rows = (
            db.query(Question.topic, func.count(Question.id).label("count"))
            .group_by(Question.topic)
            .order_by(func.count(Question.id).desc(), Question.topic.asc())
            .limit(top_n)
            .all()
        )
        top_topics = [{"topic": topic or "other", "count": count} for topic, count in topic_rows]

        recent = (
            db.query(Question)
            .order_by(Question.created_at.desc(), Question.id.desc())
            .limit(recent_n)
            .all()
        )
        recent_questions = [
            {"question": q.question_text, "is_answered": q.is_answered, "created_at": q.created_at}
            for q in recent
        ]

        return {
            "total_questions": total,
            "answered": answered,
            "unknown": unknown,
            "answer_rate": answer_rate,
            "top_topics": top_topics,
            "recent_questions": recent_questions,
        }
    finally:
        db.close()
