"""Gateway response cache (pipeline step 4): same provider + model + prompt version + input → same answer."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tubeforge.db.models import GatewayCache

DEFAULT_TTL = timedelta(days=7)


def cache_key(provider_code: str, prompt_version: str, request: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"provider": provider_code, "prompt_version": prompt_version, "request": request},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def get(db: Session, key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
    now = now or datetime.now(UTC)
    row = db.get(GatewayCache, key)
    if row is None or row.expires_at <= now:
        return None
    row.hits += 1
    db.flush()
    return dict(row.response)


def put(
    db: Session,
    key: str,
    provider_code: str,
    response: dict[str, Any],
    *,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    stmt = insert(GatewayCache).values(
        cache_key=key,
        provider_code=provider_code,
        response=response,
        created_at=now,
        expires_at=now + ttl,
        hits=0,
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[GatewayCache.cache_key],
            set_={"response": response, "created_at": now, "expires_at": now + ttl},
        )
    )
