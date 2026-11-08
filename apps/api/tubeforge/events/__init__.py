"""Real-time events for the dashboard (BACKEND_SPECIFICATION §2).

Phase 3: an in-process bus with a 24 h / 10 000-event replay buffer (``Last-Event-ID``). Events are
published by the API after its transaction commits. Worker processes (Phase 5) will feed the same
bus through PostgreSQL LISTEN/NOTIFY.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

MAX_EVENTS = 10_000
MAX_AGE_S = 24 * 3600


@dataclass(frozen=True)
class Event:
    id: int
    name: str
    data: dict[str, Any]
    at: float

    def to_sse(self) -> str:
        payload = json.dumps(self.data, separators=(",", ":"), default=str)
        return f"id: {self.id}\nevent: {self.name}\ndata: {payload}\n\n"


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: deque[Event] = deque(maxlen=MAX_EVENTS)
        self._next_id = int(time.time() * 1000)  # ids keep increasing across restarts
        self._waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = set()

    def publish(self, name: str, data: dict[str, Any]) -> Event:
        with self._lock:
            self._next_id += 1
            event = Event(id=self._next_id, name=name, data=data, at=time.time())
            self._events.append(event)
            waiters = list(self._waiters)
        for loop, flag in waiters:
            loop.call_soon_threadsafe(flag.set)
        return event

    def since(self, last_id: int | None) -> list[Event]:
        cutoff = time.time() - MAX_AGE_S
        with self._lock:
            return [e for e in self._events if e.at >= cutoff and (last_id is None or e.id > last_id)]

    def latest_id(self) -> int:
        with self._lock:
            return self._events[-1].id if self._events else self._next_id

    def subscribe(self) -> tuple[asyncio.AbstractEventLoop, asyncio.Event]:
        entry = (asyncio.get_running_loop(), asyncio.Event())
        with self._lock:
            self._waiters.add(entry)
        return entry

    def unsubscribe(self, entry: tuple[asyncio.AbstractEventLoop, asyncio.Event]) -> None:
        with self._lock:
            self._waiters.discard(entry)
