"""Usage limits with atomic reservations (COST_CONTROL_SPEC §2).

Before a call the gateway reserves an estimate (1 request + estimated tokens) against every
applicable limit — GLOBAL, per TASK and per CHANNEL, per MINUTE / DAY / MONTH — under a per-provider
advisory lock. After the call it settles the actual amount and releases the rest. ``usage_records``
is append-only: used = Σ RESERVE − Σ RELEASE for a period key; SETTLE rows record the actuals.
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from tubeforge.db.models import UsageLimit, UsageRecord

PT = "America/Los_Angeles"
REPORT_PERIODS: tuple[tuple[str, str], ...] = (("DAY", PT), ("MONTH", PT))


def period_key(period: str, tz: str, now: datetime) -> str:
    local = now.astimezone(ZoneInfo(tz))
    if period == "MINUTE":
        return local.strftime("%Y-%m-%dT%H:%M")
    if period == "DAY":
        return local.strftime("%Y-%m-%d")
    return local.strftime("%Y-%m")


def next_reset(period: str, tz: str, now: datetime) -> datetime:
    zone = ZoneInfo(tz)
    local = now.astimezone(zone)
    if period == "MINUTE":
        return (local.replace(second=0, microsecond=0) + timedelta(minutes=1)).astimezone(UTC)
    if period == "DAY":
        return datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=zone).astimezone(UTC)
    first_next = (local.replace(day=28) + timedelta(days=4)).replace(day=1)
    return datetime.combine(first_next.date(), time(0), tzinfo=zone).astimezone(UTC)


class LimitReached(Exception):  # noqa: N818 - gateway wording (LIMIT)
    def __init__(self, provider_code: str, metric: str, period: str, limit: int, resets_at: datetime) -> None:
        super().__init__(f"{provider_code}: {metric} per {period.lower()} limit {limit} reached")
        self.provider_code = provider_code
        self.metric = metric
        self.period = period
        self.limit = limit
        self.resets_at = resets_at


@dataclass
class Reservation:
    provider_code: str
    amounts: dict[str, int]
    keys: list[tuple[str, str]] = field(default_factory=list)  # (metric, period_key)
    task: str | None = None
    channel_id: uuid.UUID | None = None
    agent_run_id: uuid.UUID | None = None
    open: bool = True


def _lock(db: Session, provider_code: str) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": zlib.crc32(f"usage:{provider_code}".encode())})


def _applicable(
    db: Session, provider_code: str, task: str | None, channel_id: uuid.UUID | None
) -> list[UsageLimit]:
    rows = db.scalars(select(UsageLimit).where(UsageLimit.provider_code == provider_code)).all()

    def applies(row: UsageLimit) -> bool:
        if row.scope == "GLOBAL":
            return True
        if row.scope == "TASK":
            return row.scope_ref == task
        return channel_id is not None and row.scope_ref == str(channel_id)

    out = [row for row in rows if applies(row)]
    return out


def used(
    db: Session,
    provider_code: str,
    metric: str,
    key: str,
    *,
    task: str | None = None,
    channel_id: uuid.UUID | None = None,
) -> int:
    signed = case(
        (UsageRecord.kind == "RESERVE", UsageRecord.amount),
        (UsageRecord.kind == "RELEASE", -UsageRecord.amount),
        else_=0,
    )
    q = select(func.coalesce(func.sum(signed), 0)).where(
        UsageRecord.provider_code == provider_code,
        UsageRecord.metric == metric,
        UsageRecord.period_key == key,
    )
    if task is not None:
        q = q.where(UsageRecord.task == task)
    if channel_id is not None:
        q = q.where(UsageRecord.channel_id == channel_id)
    return int(db.scalar(q) or 0)


def reserve(
    db: Session,
    provider_code: str,
    amounts: dict[str, int],
    *,
    task: str | None = None,
    channel_id: uuid.UUID | None = None,
    agent_run_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Reservation:
    """Hold ``amounts`` (metric → n) or raise LimitReached. Runs in the caller's transaction."""
    now = now or datetime.now(UTC)
    _lock(db, provider_code)
    limits = _applicable(db, provider_code, task, channel_id)
    for lim in limits:
        if lim.metric not in amounts:
            continue
        key = period_key(lim.period, lim.reset_tz, now)
        current = used(
            db,
            provider_code,
            lim.metric,
            key,
            task=task if lim.scope == "TASK" else None,
            channel_id=channel_id if lim.scope == "CHANNEL" else None,
        )
        if current + amounts[lim.metric] > lim.limit_value:
            raise LimitReached(
                provider_code,
                lim.metric,
                lim.period,
                lim.limit_value,
                next_reset(lim.period, lim.reset_tz, now),
            )
    res = Reservation(
        provider_code, dict(amounts), task=task, channel_id=channel_id, agent_run_id=agent_run_id
    )
    periods = {(lim.period, lim.reset_tz) for lim in limits} | set(REPORT_PERIODS)
    for metric, amount in amounts.items():
        for period, tz in sorted(periods):
            key = period_key(period, tz, now)
            if (metric, key) in res.keys:
                continue
            res.keys.append((metric, key))
            _add(db, res, metric, key, amount, "RESERVE", now)
    db.flush()
    return res


def _add(db: Session, res: Reservation, metric: str, key: str, amount: int, kind: str, now: datetime) -> None:
    db.add(
        UsageRecord(
            occurred_at=now,
            provider_code=res.provider_code,
            period_key=key,
            metric=metric,
            amount=amount,
            kind=kind,
            agent_run_id=res.agent_run_id,
            channel_id=res.channel_id,
            task=res.task,
        )
    )


def settle(db: Session, res: Reservation, actual: dict[str, int], *, now: datetime | None = None) -> None:
    """Record the actual use; give back what was reserved but not used (or add an overrun)."""
    now = now or datetime.now(UTC)
    if not res.open:
        return
    for metric, key in res.keys:
        reserved = res.amounts.get(metric, 0)
        real = int(actual.get(metric, reserved))
        _add(db, res, metric, key, real, "SETTLE", now)
        if real < reserved:
            _add(db, res, metric, key, reserved - real, "RELEASE", now)
        elif real > reserved:
            _add(db, res, metric, key, real - reserved, "RESERVE", now)
    res.open = False
    db.flush()


def release(db: Session, res: Reservation, *, now: datetime | None = None) -> None:
    """The call did not happen (or failed before using anything): give everything back."""
    now = now or datetime.now(UTC)
    if not res.open:
        return
    for metric, key in res.keys:
        _add(db, res, metric, key, res.amounts.get(metric, 0), "RELEASE", now)
    res.open = False
    db.flush()
