"""YouTube error classification (§7) and PT-day arithmetic (§8)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from tubeforge.youtube.errors import ErrorClass, classify, error_reason, from_response
from tubeforge.youtube.quota import PKT, bucket_for, next_reset, pt_day


def google_error(status: int, reason: str) -> bytes:
    return json.dumps(
        {"error": {"code": status, "errors": [{"reason": reason, "domain": "youtube"}]}}
    ).encode()


@pytest.mark.parametrize(
    ("status", "reason", "expected"),
    [
        (401, None, ErrorClass.AUTH_EXPIRED),
        (400, "invalid_grant", ErrorClass.AUTH_EXPIRED),
        (401, "authError", ErrorClass.AUTH_EXPIRED),
        (403, "quotaExceeded", ErrorClass.QUOTA_EXCEEDED),
        (403, "dailyLimitExceeded", ErrorClass.QUOTA_EXCEEDED),
        (403, "rateLimitExceeded", ErrorClass.RATE_LIMITED),
        (429, None, ErrorClass.RATE_LIMITED),
        (403, "forbidden", ErrorClass.SCOPE_MISSING),
        (403, "insufficientPermissions", ErrorClass.SCOPE_MISSING),
        (400, "invalidTitle", ErrorClass.INVALID_REQUEST),
        (400, "invalidPublishAt", ErrorClass.INVALID_REQUEST),
        (400, "uploadLimitExceeded", ErrorClass.CHANNEL_LIMIT),
        (403, "videoRejected", ErrorClass.POLICY_REJECTED),
        (500, None, ErrorClass.TRANSIENT),
        (503, "backendError", ErrorClass.TRANSIENT),
        (None, None, ErrorClass.TRANSIENT),
        (404, "videoNotFound", ErrorClass.UNKNOWN),
        (400, "somethingNew", ErrorClass.UNKNOWN),
    ],
)
def test_classification_table(status: int | None, reason: str | None, expected: ErrorClass) -> None:
    assert classify(status, reason) is expected


def test_reason_is_read_from_google_and_oauth_bodies() -> None:
    assert error_reason(google_error(403, "quotaExceeded")) == "quotaExceeded"
    assert error_reason(b'{"error": "invalid_grant", "error_description": "Token has been expired"}') == (
        "invalid_grant"
    )
    assert error_reason(b"<html>bad gateway</html>") is None
    assert error_reason(None) is None
    err = from_response(403, google_error(403, "quotaExceeded"))
    assert err.error_class is ErrorClass.QUOTA_EXCEEDED and not err.retryable
    assert from_response(503, b"").retryable


def test_buckets() -> None:
    assert bucket_for("videos.insert") == "VIDEO_UPLOADS"
    assert bucket_for("search.list") == "SEARCH"
    assert bucket_for("thumbnails.set") == "DEFAULT"
    assert bucket_for("youtubeAnalytics.reports.query") == "ANALYTICS"


def test_pt_day_and_reset_follow_daylight_saving() -> None:
    # 2026-11-08 07:30 UTC = 2026-11-07 23:30 PST (DST ended 1 Nov) → still the 7th in PT.
    now = datetime(2026, 11, 8, 7, 30, tzinfo=UTC)
    assert pt_day(now) == date(2026, 11, 7)
    assert next_reset(now) == datetime(2026, 11, 8, 8, 0, tzinfo=UTC)
    assert next_reset(now).astimezone(PKT).strftime("%H:%M") == "13:00"
    # Summer (PDT, UTC-7): midnight PT = 07:00 UTC = 12:00 PKT.
    summer = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    assert next_reset(summer) == datetime(2026, 7, 2, 7, 0, tzinfo=UTC)
    assert next_reset(summer).astimezone(PKT).strftime("%H:%M") == "12:00"
