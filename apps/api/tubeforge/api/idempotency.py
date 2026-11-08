"""Idempotency-Key handling (BACKEND_SPECIFICATION §1, §6).

Same key + same request → the first response is replayed (same status and body) for 24 h.
Same key + different request → 422 IDEMPOTENCY_MISMATCH. The key row is written in the same
transaction as the work, so a failed request leaves no key behind.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from tubeforge.api.errors import ProblemError
from tubeforge.db.models import IdempotencyKey

HEADER = "Idempotency-Key"
TTL = timedelta(hours=24)


class Idempotency:
    def __init__(self, db: Session, request: Request, user_id: uuid.UUID, body: Any) -> None:
        raw = request.headers.get(HEADER)
        if not raw:
            raise ProblemError(
                400,
                "IDEMPOTENCY_KEY_REQUIRED",
                "Missing Idempotency-Key",
                "This action needs an Idempotency-Key header (a UUID).",
            )
        try:
            self.key = uuid.UUID(raw)
        except ValueError as exc:
            raise ProblemError(
                400, "VALIDATION_ERROR", "Invalid request", "Idempotency-Key must be a UUID."
            ) from exc
        self.db, self.user_id = db, user_id
        canonical = json.dumps(jsonable_encoder(body), sort_keys=True, separators=(",", ":"))
        self.request_hash = hashlib.sha256(
            f"{request.method} {request.url.path} {canonical}".encode()
        ).hexdigest()
        self.method, self.path = request.method, request.url.path
        self.row: IdempotencyKey | None = None

    def replay(self) -> JSONResponse | None:
        """Return the stored response for a repeated request, or None for a new one."""
        existing = self.db.get(IdempotencyKey, (self.user_id, self.key))
        now = datetime.now(UTC)
        if existing is not None and existing.expires_at <= now:
            self.db.delete(existing)
            self.db.flush()
            existing = None
        if existing is None:
            self.row = IdempotencyKey(
                user_id=self.user_id,
                key=self.key,
                method=self.method,
                path=self.path,
                request_sha256=self.request_hash,
                expires_at=now + TTL,
            )
            self.db.add(self.row)
            self.db.flush()
            return None
        if existing.request_sha256 != self.request_hash:
            raise ProblemError(
                422,
                "IDEMPOTENCY_MISMATCH",
                "Key already used",
                "This Idempotency-Key was used for a different request.",
            )
        if existing.status_code is None:
            raise ProblemError(
                409, "IDEMPOTENCY_IN_PROGRESS", "Still running", "The first request is still running."
            )
        return JSONResponse(
            existing.response_body, status_code=existing.status_code, headers={"Idempotency-Replayed": "true"}
        )

    def store(self, status_code: int, body: Any) -> None:
        if self.row is not None:
            self.row.status_code = status_code
            self.row.response_body = jsonable_encoder(body)
