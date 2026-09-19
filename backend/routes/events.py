from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from backend import events

router = APIRouter(prefix="/api", tags=["events"])


@router.get(
    "/events",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "SSE stream. `event: turn` carries a Turn, `event: dataset` a "
            "DatasetInfo, `event: ping` is a keepalive every 15s.",
            "content": {"text/event-stream": {}},
        }
    },
)
async def stream_events() -> EventSourceResponse:
    queue = events.subscribe()

    async def gen() -> AsyncIterator[dict]:
        try:
            while True:
                event, data = await queue.get()
                yield {"event": event.value, "data": data}
        finally:
            events.unsubscribe(queue)

    return EventSourceResponse(gen(), ping=15)
