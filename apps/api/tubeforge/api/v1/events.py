"""Server-sent events: GET /api/v1/events/stream (BACKEND_SPECIFICATION §2)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from tubeforge.api.deps import Principal, authenticated
from tubeforge.events import EventBus

router = APIRouter(tags=["events"])
HEARTBEAT_S = 15.0


async def _stream(request: Request, bus: EventBus, last_id: int | None) -> AsyncIterator[str]:
    idle_limit: float | None = request.app.state.sse_idle_limit_s  # tests only; None = stream forever
    entry = bus.subscribe()
    _, flag = entry
    try:
        yield "retry: 3000\n\n"
        cursor = last_id if last_id is not None else bus.latest_id()
        for event in bus.since(last_id) if last_id is not None else []:
            yield event.to_sse()
            cursor = event.id
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            flag.clear()
            fresh = bus.since(cursor)
            if fresh:
                for event in fresh:
                    yield event.to_sse()
                    cursor = event.id
                idle = 0.0
                continue
            wait = HEARTBEAT_S if idle_limit is None else min(HEARTBEAT_S, idle_limit)
            try:
                await asyncio.wait_for(flag.wait(), timeout=wait)
            except TimeoutError:
                idle += wait
                if idle_limit is not None and idle >= idle_limit:
                    return
                yield ": heartbeat\n\n"
    finally:
        bus.unsubscribe(entry)


@router.get("/events/stream", response_class=StreamingResponse)
async def event_stream(
    request: Request,
    _: Annotated[Principal, Depends(authenticated)],
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    bus: EventBus = request.app.state.events
    try:
        last = int(last_event_id) if last_event_id else None
    except ValueError:
        last = None
    return StreamingResponse(
        _stream(request, bus, last),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
