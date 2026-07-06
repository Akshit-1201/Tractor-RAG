"""Public chat router (spec §10.5). JSON mode by default; SSE when the client
sends `Accept: text/event-stream`. The SSE path strips the `CITED: [...]`
trailer from forwarded tokens — customers must never see it.
"""

import json
import logging
import time
from typing import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.ratelimit import limiter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat as chat_service
from app.services import retrieval
from app.services.chat import format_numbered_context

logger = logging.getLogger(__name__)

router = APIRouter()

_HOLD = 8  # ≥ len("\nCITED") so a trailer split across tokens can't leak


def _result_response(result: chat_service.ChatResult) -> ChatResponse:
    return ChatResponse(
        answer=result.answer,
        is_answered=result.is_answered,
        sources=result.sources,
        image=result.image,
    )


def _token_event(text: str) -> str:
    return f"event: token\ndata: {json.dumps({'text': text})}\n\n"


def _sse_stream(question: str, history: list[dict]) -> Iterator[str]:
    started = time.perf_counter()
    try:
        standalone = chat_service.resolve_standalone(question, history)
        chunks = retrieval.retrieve(standalone)
        raw_parts: list[str] = []
        pending = ""
        trailer_found = False
        emitted_any = False

        if chunks:
            context = format_numbered_context(chunks)
            for token in chat_service.stream_llm(context, standalone):
                raw_parts.append(token)
                if trailer_found:
                    continue  # keep accumulating raw for parsing; emit nothing
                pending += token
                marker = pending.upper().rfind("\nCITED")
                if marker != -1:
                    if pending[:marker]:
                        yield _token_event(pending[:marker])
                        emitted_any = True
                    pending = ""
                    trailer_found = True
                elif len(pending) > _HOLD:
                    if not emitted_any and pending.lstrip().upper().startswith("CITED"):
                        # answer-less output: the entire stream is the trailer
                        trailer_found = True
                        pending = ""
                        continue
                    yield _token_event(pending[:-_HOLD])
                    emitted_any = True
                    pending = pending[-_HOLD:]
            # flush the held tail unless it is itself a CITED line
            if not trailer_found and pending and not pending.lstrip().upper().startswith("CITED"):
                yield _token_event(pending)

        raw = "".join(raw_parts)
        result = chat_service.finalize(question, chunks, raw, started)
        # The final event carries the canonical answer too, so the UI can replace
        # streamed text (e.g. with the exact IDK string) — spec §8.5.
        yield f"event: final\ndata: {_result_response(result).model_dump_json()}\n\n"
    except Exception:
        logger.exception("SSE chat stream failed")
        yield f"event: error\ndata: {json.dumps({'detail': 'The assistant is temporarily unavailable.'})}\n\n"


@router.post("/chat")
@limiter.limit(settings.CHAT_RATE_LIMIT)
def chat_endpoint(request: Request, body: ChatRequest):
    history = [{"role": turn.role, "content": turn.content} for turn in body.history]
    if "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(
            _sse_stream(body.question, history), media_type="text/event-stream"
        )
    return _result_response(chat_service.answer_question(body.question, history))
