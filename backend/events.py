"""In-process pub/sub feeding GET /api/events (single-user demo, no persistence).

Publishers may run in worker threads (sync routes), so delivery goes through each
subscriber's event loop.
"""

import asyncio

from backend.contract import DatasetInfo, SseEvent, Turn

Item = tuple[SseEvent, str]
_subscribers: dict[asyncio.Queue[Item], asyncio.AbstractEventLoop] = {}
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
    for queue, loop in list(_subscribers.items()):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (event, data))
        except RuntimeError:  # loop closed
            _subscribers.pop(queue, None)


def subscribe() -> asyncio.Queue[Item]:
    queue: asyncio.Queue[Item] = asyncio.Queue()
    _subscribers[queue] = asyncio.get_running_loop()
    return queue


def unsubscribe(queue: asyncio.Queue[Item]) -> None:
    _subscribers.pop(queue, None)
