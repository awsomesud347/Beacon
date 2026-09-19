"""OpenAI-compatible chat completions endpoint for the ElevenLabs agent (custom LLM).

Only the last user message is used. The narration is fully generated and guard-checked
before streaming starts; it is then streamed one sentence per chunk.
"""

import json
import re
import secrets
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from backend import stub
from backend.config import get_settings
from backend.contract import ApiError, Channel, ChatCompletionRequest, ErrorCode
from backend.errors import ApiException, not_implemented

router = APIRouter(prefix="/v1", tags=["llm-proxy"])

MODEL_NAME = "beacon"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def sse_chunks(narration: str, completion_id: str, created: int) -> Iterator[str]:
    def chunk(delta: dict, finish: str | None = None) -> str:
        body = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": MODEL_NAME,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(body)}\n\n"

    sentences = split_sentences(narration)
    for i, sentence in enumerate(sentences):
        content = sentence if i == len(sentences) - 1 else sentence + " "
        delta = {"role": "assistant", "content": content} if i == 0 else {"content": content}
        yield chunk(delta)
    yield chunk({}, "stop")
    yield "data: [DONE]\n\n"


def completion_body(narration: str, completion_id: str, created: int) -> dict:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": narration},
                "finish_reason": "stop",
            }
        ],
    }


def last_user_text(req: ChatCompletionRequest) -> str:
    for msg in reversed(req.messages):
        if msg.role != "user":
            continue
        if isinstance(msg.content, str):
            return msg.content
        if isinstance(msg.content, list):
            return " ".join(p.get("text", "") for p in msg.content if isinstance(p, dict))
    return ""


def check_auth(authorization: str | None) -> None:
    expected = get_settings().llm_proxy_secret
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not expected or not secrets.compare_digest(token, expected):
        raise ApiException(401, ErrorCode.unauthorized, "Invalid or missing proxy secret")


def respond(narration: str, stream: bool):
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    if stream:
        return StreamingResponse(
            sse_chunks(narration, completion_id, created), media_type="text/event-stream"
        )
    return completion_body(narration, completion_id, created)


@router.post(
    "/chat/completions",
    responses={
        200: {
            "description": "chat.completion JSON, or an SSE stream of chat.completion.chunk "
            "objects ending in `data: [DONE]` when stream=true.",
            "content": {"text/event-stream": {}},
        },
        401: {"model": ApiError},
    },
)
def chat_completions(req: ChatCompletionRequest, authorization: str | None = Header(None)):
    check_auth(authorization)
    if get_settings().stub_mode:
        turn = stub.query(last_user_text(req), Channel.voice)
        return respond(turn.narration, req.stream)
    raise not_implemented("chat completions")
