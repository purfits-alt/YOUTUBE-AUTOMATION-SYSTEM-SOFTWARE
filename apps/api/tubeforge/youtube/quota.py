"""Quota ledger, reservations, PT day and forecasts (YOUTUBE_API_INTEGRATION §8).

Limits and method costs come from ``quota_config`` (seeded by migration 0004 with the costs verified
on 2026-11-08), never from code. Each Cloud project has its own rows; a project without rows uses the
``default`` rows. Reservations are serialised per (project, PT day, bucket) with a transaction-level
advisory lock, so two workers cannot both take the last unit.
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import QuotaConfig, QuotaLedger, QuotaReservation

PT = ZoneInfo("America/Los_Angeles")
PKT = ZoneInfo("Asia/Karachi")
DEFAULT_PROJECT = "default"
RESERVATION_TTL = timedelta(minutes=30)
BUCKETS = ("VIDEO_UPLOADS", "SEARCH", "DEFAULT", "ANALYTICS")


class QuotaError(Exception):
    """Configuration problem (unknown method or bucket without a limit)."""


class QuotaExhausted(Exception):  # noqa: N818 - domain wording (WAITING_QUOTA)
    def __init__(self, bucket: str, needed: int, available: int, resets_at: datetime) -> None:
        super().__init__(f"{bucket}: needs {needed}, {available} left until {resets_at.isoformat()}")
        self.bucket = bucket
        self.needed = needed
        self.available = available
        self.resets_at = resets_at


def pt_day(now: datetime) -> date:
    """The America/Los_Angeles calendar day (YouTube quota resets at midnight PT)."""
    return now.astimezone(PT).date()


def next_reset(now: datetime) -> datetime:
    """The next midnight PT, as an aware UTC datetime (daylight saving handled by zoneinfo)."""
    tomorrow = pt_day(now) + timedelta(days=1)
    return datetime.combine(tomorrow, time(0), tzinfo=PT).astimezone(UTC)


def bucket_for(method: str) -> str:
    if method == "videos.insert":
        return "VIDEO_UPLOADS"
    if method == "search.list":
        return "SEARCH"
    if method.startswith("youtubeAnalytics."):
        return "ANALYTICS"
    return "DEFAULT"


def _config(db: Session, project: str, bucket: str) -> QuotaConfig:
    row = db.get(QuotaConfig, (project, bucket)) or db.get(QuotaConfig, (DEFAULT_PROJECT, bucket))
    if row is None:
        raise QuotaError(f"no quota_config row for bucket {bucket}; the owner enters it in Settings")
    return row


def method_cost(db: Session, project: str, method: str) -> int:
    costs = _config(db, project, bucket_for(method)).method_costs
    if method not in costs:
        raise QuotaError(f"the cost of {method} is not configured in quota_config")
    return int(costs[method])


def _lock(db: Session, project: str, day: date, bucket: str) -> None:
    key = zlib.crc32(f"quota:{project}:{day.isoformat()}:{bucket}".encode())
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def _used(db: Session, project: str, day: date, bucket: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(QuotaLedger.units), 0)).where(
                QuotaLedger.gcp_project == project, QuotaLedger.pt_day == day, QuotaLedger.bucket == bucket
            )
        )
        or 0
    )


def _held(
    db: Session, project: str, day: date, bucket: str, now: datetime, purpose: str | None = None
) -> int:
    q = select(func.coalesce(func.sum(QuotaReservation.units), 0)).where(
        QuotaReservation.gcp_project == project,
        QuotaReservation.pt_day == day,
        QuotaReservation.bucket == bucket,
        QuotaReservation.state == "HELD",
        QuotaReservation.expires_at > now,
    )
    if purpose is not None:
        q = q.where(QuotaReservation.purpose == purpose)
    return int(db.scalar(q) or 0)


def _research_used(db: Session, project: str, day: date, now: datetime) -> int:
    settled = db.scalar(
        select(func.coalesce(func.sum(QuotaLedger.units), 0))
        .join(QuotaReservation, QuotaReservation.id == QuotaLedger.reservation_id)
        .where(
            QuotaLedger.gcp_project == project,
            QuotaLedger.pt_day == day,
            QuotaLedger.bucket == "SEARCH",
            QuotaReservation.purpose == "research",
        )
    )
    return int(settled or 0) + _held(db, project, day, "SEARCH", now, purpose="research")


@dataclass(frozen=True)
class BucketStatus:
    bucket: str
    daily_limit: int
    usable: int  # limit minus the reserve %
    used: int
    held: int
    available: int
    resets_at: datetime
    resets_at_pkt: str


def status(db: Session, project: str, now: datetime | None = None) -> list[BucketStatus]:
    now = now or datetime.now(UTC)
    day = pt_day(now)
    reset = next_reset(now)
    out: list[BucketStatus] = []
    for bucket in BUCKETS:
        try:
            cfg = _config(db, project, bucket)
        except QuotaError:
            continue
        usable = cfg.daily_limit * (100 - cfg.reserve_pct) // 100
        used = _used(db, project, day, bucket)
        held = _held(db, project, day, bucket, now)
        out.append(
            BucketStatus(
                bucket=bucket,
                daily_limit=cfg.daily_limit,
                usable=usable,
                used=used,
                held=held,
                available=max(0, usable - used - held),
                resets_at=reset,
                resets_at_pkt=reset.astimezone(PKT).strftime("%H:%M PKT"),
            )
        )
    return out


def reserve(
    db: Session,
    *,
    project: str,
    method: str,
    calls: int = 1,
    purpose: str,
    job_id: str | None = None,
    now: datetime | None = None,
) -> QuotaReservation:
    """Hold quota for ``calls`` calls of ``method`` (I-10). Raises QuotaExhausted → WAITING_QUOTA."""
    now = now or datetime.now(UTC)
    bucket = bucket_for(method)
    units = method_cost(db, project, method) * calls
    day = pt_day(now)
    _lock(db, project, day, bucket)
    cfg = _config(db, project, bucket)
    usable = cfg.daily_limit * (100 - cfg.reserve_pct) // 100
    available = usable - _used(db, project, day, bucket) - _held(db, project, day, bucket, now)
    if bucket == "SEARCH" and purpose == "research":
        share = cfg.daily_limit * cfg.research_share_pct // 100
        available = min(available, share - _research_used(db, project, day, now))
    if units > available:
        raise QuotaExhausted(bucket, units, max(0, available), next_reset(now))
    row = QuotaReservation(
        id=uuid7(),
        gcp_project=project,
        pt_day=day,
        bucket=bucket,
        units=units,
        purpose=purpose,
        job_id=job_id,
        state="HELD",
        expires_at=now + RESERVATION_TTL,
    )
    db.add(row)
    db.flush()
    return row


def record_call(
    db: Session,
    *,
    project: str,
    method: str,
    reservation: QuotaReservation | None = None,
    channel_id: uuid.UUID | None = None,
    job_id: str | None = None,
    http_status: int | None = None,
    error_reason: str | None = None,
    now: datetime | None = None,
) -> QuotaLedger:
    """Write one ledger row for a call that reached Google (even a failed one costs ≥ 1 unit).

    If a reservation is given it is settled; the ledger keeps the configured cost of one call.
    """
    now = now or datetime.now(UTC)
    units = max(1, method_cost(db, project, method))
    row = QuotaLedger(
        occurred_at=now,
        pt_day=pt_day(now),
        gcp_project=project,
        bucket=bucket_for(method),
        method=method,
        units=units,
        reservation_id=reservation.id if reservation else None,
        channel_id=channel_id,
        job_id=job_id,
        http_status=http_status,
        error_reason=error_reason,
    )
    db.add(row)
    if reservation is not None:
        reservation.units = max(0, reservation.units - units)
        if reservation.units == 0:
            reservation.state = "SETTLED"
    db.flush()
    return row


def release(db: Session, reservation: QuotaReservation) -> None:
    """Give back what was not used (failure before the call, or the job finished early)."""
    if reservation.state == "HELD":
        reservation.state = "RELEASED" if reservation.units else "SETTLED"
        db.flush()


def exhaust(db: Session, *, project: str, bucket: str, now: datetime | None = None) -> None:
    """Google said quotaExceeded: hold the rest of today's bucket so nothing else tries until reset."""
    now = now or datetime.now(UTC)
    day = pt_day(now)
    _lock(db, project, day, bucket)
    cfg = _config(db, project, bucket)
    left = cfg.daily_limit - _used(db, project, day, bucket) - _held(db, project, day, bucket, now)
    if left > 0:
        db.add(
            QuotaReservation(
                id=uuid7(),
                gcp_project=project,
                pt_day=day,
                bucket=bucket,
                units=left,
                purpose="quota-exceeded",
                state="HELD",
                expires_at=next_reset(now),
            )
        )
        db.flush()


@dataclass(frozen=True)
class Forecast:
    day: date
    planned_uploads: int
    upload_calls_left: int
    default_units_needed: int
    default_units_usable: int
    ok: bool


PACKAGE_METHODS = ("thumbnails.set", "captions.insert", "playlistItems.insert", "videos.update")


def package_cost(db: Session, project: str) -> int:
    """≈ 550 units: the post-upload steps of one full publish package (§3)."""
    return sum(method_cost(db, project, m) for m in PACKAGE_METHODS)


def forecast(db: Session, project: str, planned: dict[date, int]) -> list[Forecast]:
    """Planned uploads per PT day against capacity (the daily job feeds this from the schedule)."""
    up = _config(db, project, "VIDEO_UPLOADS")
    df = _config(db, project, "DEFAULT")
    per_package = package_cost(db, project)
    up_usable = up.daily_limit * (100 - up.reserve_pct) // 100
    df_usable = df.daily_limit * (100 - df.reserve_pct) // 100
    out = []
    for day in sorted(planned):
        n = planned[day]
        need = n * per_package
        out.append(
            Forecast(
                day=day,
                planned_uploads=n,
                upload_calls_left=up_usable - n,
                default_units_needed=need,
                default_units_usable=df_usable,
                ok=n <= up_usable and need <= df_usable,
            )
        )
    return out
