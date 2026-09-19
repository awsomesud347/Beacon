"""In-process pub/sub feeding GET /api/events (single-user demo, no persistence)."""

import asyncio

from backend.contract import DatasetInfo, SseEvent, Turn

_subscribers: set[asyncio.Queue[tuple[SseEvent, str]]] = set()
_latest_turn: Turn | None = None


def latest_turn() -> Turn | None:
    return _latest_turn


def publish_turn(turn: Turn) -> None:
    global _latest_turn
    _latest_turn = turn
    _broadcast(SseEvent.turn, turn.model_dump_json())


def publish_dataset(info: DatasetInfo) -> None:
    _broadcast(SseEvent.dataset, info.model_dump_json())


def _broadcast(event: SseEvent, data: str) -> None:
    for queue in list(_subscribers):
        queue.put_nowait((event, data))


def subscribe() -> asyncio.Queue[tuple[SseEvent, str]]:
    queue: asyncio.Queue[tuple[SseEvent, str]] = asyncio.Queue()
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[tuple[SseEvent, str]]) -> None:
    _subscribers.discard(queue)
