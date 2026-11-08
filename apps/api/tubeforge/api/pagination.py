"""Cursor pagination (BACKEND_SPECIFICATION §1): ``?limit=50&cursor=<opaque>`` → ``{items, next_cursor}``.

Clients must treat the cursor as opaque. Its documented pattern (``c`` + digits) means every value
that matches the schema is accepted; anything else is rejected by validation (400).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
CURSOR_PATTERN = r"^c[0-9]{1,18}$"

Cursor = Annotated[
    str | None,
    Query(pattern=CURSOR_PATTERN, description="Opaque cursor: pass back the previous page's next_cursor."),
]
Limit = Annotated[int | None, Query(ge=1, le=MAX_LIMIT)]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


def encode_cursor(last_id: int) -> str:
    return f"c{last_id}"


def decode_cursor(cursor: str | None) -> int | None:
    return int(cursor[1:]) if cursor else None


def clamp_limit(limit: int | None) -> int:
    return max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT))
