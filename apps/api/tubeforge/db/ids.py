"""UUIDv7 identifiers (DATABASE_SCHEMA §0: time-ordered, generated in the application)."""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit Unix ms | version 7 | 12 random bits | variant 10 | 62 random bits."""
    ms = time.time_ns() // 1_000_000
    rand_a = int.from_bytes(os.urandom(2), "big") & 0xFFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = ((ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)
