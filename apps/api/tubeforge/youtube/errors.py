"""Classify YouTube Data API and Google OAuth errors (YOUTUBE_API_INTEGRATION §7)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any


class ErrorClass(StrEnum):
    AUTH_EXPIRED = "AUTH_EXPIRED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    SCOPE_MISSING = "SCOPE_MISSING"
    INVALID_REQUEST = "INVALID_REQUEST"
    CHANNEL_LIMIT = "CHANNEL_LIMIT"
    POLICY_REJECTED = "POLICY_REJECTED"
    TRANSIENT = "TRANSIENT"
    UNKNOWN = "UNKNOWN"


# Retry policy per class: (retry automatically, max attempts). The caller decides the waiting.
RETRYABLE: dict[ErrorClass, int] = {ErrorClass.RATE_LIMITED: 5, ErrorClass.TRANSIENT: 8}

_AUTH = {"invalid_grant", "autherror", "unauthorized", "invalid_token"}
_QUOTA = {"quotaexceeded", "dailylimitexceeded"}
_RATE = {"ratelimitexceeded", "userratelimitexceeded"}
_SCOPE = {"forbidden", "insufficientpermissions", "access_denied"}
_INVALID = {
    "invalidmetadata",
    "invalidtitle",
    "invaliddescription",
    "invalidtags",
    "invalidcategoryid",
    "invalidpublishat",
    "invalidvideometadata",
    "mediabodyrequired",
}
_CHANNEL = {"uploadlimitexceeded"}
_POLICY = {"videorejected", "rejected"}


class YouTubeApiError(Exception):
    """A classified failure from Google. ``detail`` is safe to log (no tokens, no bodies we sent)."""

    def __init__(self, error_class: ErrorClass, status: int | None, reason: str | None, detail: str) -> None:
        super().__init__(f"{error_class}: {detail}")
        self.error_class = error_class
        self.status = status
        self.reason = reason
        self.detail = detail

    @property
    def retryable(self) -> bool:
        return self.error_class in RETRYABLE


def error_reason(body: str | bytes | dict[str, Any] | None) -> str | None:
    """The first ``reason`` from a Google error body, or the OAuth ``error`` code."""
    if body is None:
        return None
    data: Any = body
    if isinstance(body, (str, bytes)):
        try:
            data = json.loads(body)
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    err = data.get("error")
    if isinstance(err, str):  # OAuth token endpoint: {"error": "invalid_grant", ...}
        return err
    if isinstance(err, dict):
        for item in err.get("errors") or []:
            if isinstance(item, dict) and isinstance(item.get("reason"), str):
                return str(item["reason"])
        status = err.get("status")
        if isinstance(status, str):
            return status
    return None


def classify(status: int | None, reason: str | None = None) -> ErrorClass:
    """Map an HTTP status and Google reason to an error class. ``status=None`` = network failure."""
    r = (reason or "").lower()
    if status is None:
        return ErrorClass.TRANSIENT
    if r in _QUOTA:
        return ErrorClass.QUOTA_EXCEEDED
    if r in _RATE or status == 429:
        return ErrorClass.RATE_LIMITED
    if r in _CHANNEL:
        return ErrorClass.CHANNEL_LIMIT
    if r in _POLICY:
        return ErrorClass.POLICY_REJECTED
    if status == 401 or r in _AUTH:
        return ErrorClass.AUTH_EXPIRED
    if status == 403 and (r in _SCOPE or not r):
        return ErrorClass.SCOPE_MISSING
    if status == 400 and r in _INVALID:
        return ErrorClass.INVALID_REQUEST
    if status in (500, 502, 503, 504) or r in {"backenderror", "internalerror"}:
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN


def from_response(status: int, body: str | bytes | None) -> YouTubeApiError:
    reason = error_reason(body)
    cls = classify(status, reason)
    return YouTubeApiError(cls, status, reason, f"HTTP {status}" + (f" {reason}" if reason else ""))
