from datetime import datetime

from pydantic import BaseModel


class TopicCount(BaseModel):
    topic: str
    count: int


class RecentQuestion(BaseModel):
    question: str
    is_answered: bool
    created_at: datetime


class AnalyticsResponse(BaseModel):
    """Shape from spec §10.4."""

    total_questions: int
    answered: int
    unknown: int
    answer_rate: float
    top_topics: list[TopicCount]
    recent_questions: list[RecentQuestion]
