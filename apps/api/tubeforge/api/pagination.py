"""Cursor pagination (BACKEND_SPECIFICATION §1): ``?limit=50&cursor=<opaque>`` → ``{items, next_cursor}``."""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel

from tubeforge.api.errors import ProblemError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


def encode_cursor(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProblemError(400, "VALIDATION_ERROR", "Invalid request", "The cursor is not valid.") from exc
    if not isinstance(value, dict):
        raise ProblemError(400, "VALIDATION_ERROR", "Invalid request", "The cursor is not valid.")
    return value


def clamp_limit(limit: int | None) -> int:
    return max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT))
