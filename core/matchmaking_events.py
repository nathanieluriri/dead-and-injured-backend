from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
_lock = asyncio.Lock()


async def publish(user_id: str, event: dict[str, Any]) -> None:
    async with _lock:
        queues = list(_subscribers.get(user_id, []))
    for queue in queues:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


@asynccontextmanager
async def subscribe(user_id: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
    async with _lock:
        _subscribers.setdefault(user_id, []).append(queue)
    try:
        yield queue
    finally:
        async with _lock:
            queues = _subscribers.get(user_id)
            if queues is not None:
                try:
                    queues.remove(queue)
                except ValueError:
                    pass
                if not queues:
                    _subscribers.pop(user_id, None)
