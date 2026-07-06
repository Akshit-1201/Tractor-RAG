from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings


class HistoryTurn(BaseModel):
    """One prior turn the client replays for follow-up understanding. Used only to
    rewrite the new question into a standalone one — never as an answer source."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=settings.MAX_HISTORY_CHARS)


class ChatRequest(BaseModel):
    # max_length gives an automatic 422 before any OpenAI call (spec §15)
    question: str = Field(..., min_length=1, max_length=settings.MAX_QUESTION_CHARS)
    # recent conversation the client replays; capped so it can't blow up tokens/cost
    history: list[HistoryTurn] = Field(
        default_factory=list, max_length=settings.MAX_HISTORY_MESSAGES
    )


class Source(BaseModel):
    type: str  # 'document' | 'image'
    name: str
    chunk_id: int


class ImageRef(BaseModel):
    url: str
    caption: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    is_answered: bool
    sources: list[Source]
    image: Optional[ImageRef] = None
