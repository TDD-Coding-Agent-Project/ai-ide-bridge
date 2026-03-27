from __future__ import annotations

import asyncio
from collections import defaultdict

from app.models.event import EventEnvelope
from app.models.common import EventType


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[EventEnvelope]]] = defaultdict(list)
        self._history: dict[str, list[EventEnvelope]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)

    def subscribe(self, task_id: str) -> asyncio.Queue[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._subscribers[task_id].append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[EventEnvelope]) -> None:
        subscribers = self._subscribers.get(task_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

    def get_history(self, task_id: str) -> list[EventEnvelope]:
        return list(self._history.get(task_id, []))

    async def publish(
        self,
        task_id: str,
        event_type: EventType,
        payload: dict,
    ) -> EventEnvelope:
        self._seq[task_id] += 1
        event = EventEnvelope(
            taskId=task_id,
            seq=self._seq[task_id],
            type=event_type,
            payload=payload,
        )
        self._history[task_id].append(event)

        for queue in self._subscribers.get(task_id, []):
            await queue.put(event)

        return event