"""Paid providers (Tier P): two-step activation, monthly budgets, cost debits (COST_CONTROL_SPEC §3).

- **Step 1** (owner, after re-auth): acknowledge that it costs money → ``paid_activation_step = 1``.
- **Step 2** (separate request, at least 60 s and at most 30 min later, re-auth): type
  ``ENABLE PAID <code>`` and set a monthly cap > 0 → step 2, enabled, budget row for this month.
- Every paid call is estimated before it is sent and debited after; at the cap the provider pauses.
- Disabling is one call and immediate; re-enabling repeats both steps.
The step-1 time is read from the tamper-evident audit log, not from a column a bug could rewrite.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.audit import Actor, record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import AuditLog, CostBudget, ProviderRegistry
from tubeforge.notifications import notify_owners

STEP_GAP = timedelta(seconds=60)
STEP_WINDOW = timedelta(minutes=30)


class PaidActivationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def month_key(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y-%m")


def confirm_phrase(code: str) -> str:
    return f"ENABLE PAID {code}"


def _paid_provider(db: Session, code: str) -> ProviderRegistry:
    row = db.get(ProviderRegistry, code, with_for_update=True)
    if row is None:
        raise PaidActivationError("NOT_FOUND", "No such provider.")
    if row.tier != "P":
        raise PaidActivationError("NOT_PAID", "Only paid (Tier P) providers use this activation.")
    return row


def cost_estimate(row: ProviderRegistry) -> dict[str, Any]:
    """What step 1 shows the owner: price per million tokens and a typical video, from the registry."""
    lim = row.limits or {}
    pin, pout = lim.get("price_in_per_mtok_minor"), lim.get("price_out_per_mtok_minor")
    typical = None
    if pin is not None and pout is not None:
        typical = cost_minor(row, 60_000, 15_000)  # a long-form video's agent calls, roughly
    return {
        "currency": lim.get("currency", "USD"),
        "price_in_per_mtok_minor": pin,
        "price_out_per_mtok_minor": pout,
        "typical_video_minor": typical,
        "pricing_url": row.verified_url,
        "verified_at": row.verified_at.isoformat(),
    }


def step1(db: Session, code: str, *, actor: Actor, now: datetime | None = None) -> ProviderRegistry:
    now = now or datetime.now(UTC)
    row = _paid_provider(db, code)
    row.paid_activation_step = 1
    row.enabled = False
    record(
        db,
        actor=actor,
        action="provider.paid_step1",
        entity_type="provider",
        entity_id=code,
        details=cost_estimate(row),
    )
    security_event(db, "PAID_ACTIVATION_STEP1", "WARNING", details={"provider": code})
    db.flush()
    return row


def _step1_time(db: Session, code: str) -> datetime | None:
    return db.scalar(
        select(AuditLog.occurred_at)
        .where(AuditLog.action == "provider.paid_step1", AuditLog.entity_id == code)
        .order_by(AuditLog.id.desc())
        .limit(1)
    )


def step2(
    db: Session,
    code: str,
    *,
    phrase: str,
    monthly_cap_minor: int,
    actor: Actor,
    now: datetime | None = None,
) -> ProviderRegistry:
    now = now or datetime.now(UTC)
    row = _paid_provider(db, code)
    if row.paid_activation_step != 1:
        raise PaidActivationError("STEP1_REQUIRED", "Do step 1 first.")
    started = _step1_time(db, code)
    if started is None or now - started < STEP_GAP:
        raise PaidActivationError("TOO_SOON", "Wait at least 60 seconds after step 1, then confirm again.")
    if now - started > STEP_WINDOW:
        row.paid_activation_step = 0
        raise PaidActivationError("STEP1_EXPIRED", "Step 1 is older than 30 minutes; start again.")
    if phrase.strip() != confirm_phrase(code):
        raise PaidActivationError("PHRASE_MISMATCH", f"Type exactly: {confirm_phrase(code)}")
    if monthly_cap_minor <= 0:
        raise PaidActivationError("CAP_REQUIRED", "Set a monthly cap above zero.")
    row.paid_activation_step = 2
    row.enabled = True
    set_cap(db, scope="PAID_PROVIDER", provider_code=code, cap_minor=monthly_cap_minor, now=now)
    record(
        db,
        actor=actor,
        action="provider.paid_enabled",
        entity_type="provider",
        entity_id=code,
        details={"monthly_cap_minor": monthly_cap_minor},
    )
    security_event(
        db, "PAID_PROVIDER_ENABLED", "CRITICAL", details={"provider": code, "cap_minor": monthly_cap_minor}
    )
    notify_owners(
        db,
        event_type="cost.paid_enabled",
        severity="WARNING",
        title="A paid provider is now enabled",
        body=f"{code} can now cost money, up to {monthly_cap_minor / 100:.2f} per month.",
        dedup_key=f"cost.paid_enabled:{code}:{now.isoformat()}",
        link="/usage",
        now=now,
    )
    db.flush()
    return row


def disable(db: Session, code: str, *, actor: Actor) -> ProviderRegistry:
    """One click, immediate. Re-enabling needs both steps again."""
    row = _paid_provider(db, code)
    row.enabled = False
    row.paid_activation_step = 0
    record(db, actor=actor, action="provider.paid_disabled", entity_type="provider", entity_id=code)
    db.flush()
    return row


# ------------------------------------------------------------------------------------------ budgets
def budget(
    db: Session, *, scope: str, provider_code: str | None, now: datetime | None = None
) -> CostBudget | None:
    now = now or datetime.now(UTC)
    q = select(CostBudget).where(CostBudget.scope == scope, CostBudget.month == month_key(now))
    q = (
        q.where(CostBudget.provider_code == provider_code)
        if provider_code
        else q.where(CostBudget.provider_code.is_(None))
    )
    return db.scalar(q.with_for_update())


def set_cap(
    db: Session, *, scope: str, provider_code: str | None, cap_minor: int, now: datetime | None = None
) -> CostBudget:
    now = now or datetime.now(UTC)
    if cap_minor < 0:
        raise PaidActivationError("CAP_INVALID", "A cap cannot be negative.")
    row = budget(db, scope=scope, provider_code=provider_code, now=now)
    if row is None:
        row = CostBudget(
            id=uuid7(), scope=scope, provider_code=provider_code, month=month_key(now), cap_minor=cap_minor
        )
        db.add(row)
    else:
        if cap_minor < row.spent_minor:
            raise PaidActivationError(
                "CAP_BELOW_SPENT", "The cap cannot be lower than what was already spent this month."
            )
        row.cap_minor = cap_minor
    db.flush()
    return row


def remaining_minor(db: Session, provider_code: str, now: datetime | None = None) -> int:
    row = budget(db, scope="PAID_PROVIDER", provider_code=provider_code, now=now)
    return 0 if row is None else max(0, row.cap_minor - row.spent_minor)


def cost_minor(row: ProviderRegistry, tokens_in: int, tokens_out: int) -> int | None:
    lim = row.limits or {}
    pin, pout = lim.get("price_in_per_mtok_minor"), lim.get("price_out_per_mtok_minor")
    if pin is None or pout is None:
        return None
    return math.ceil((tokens_in * float(pin) + tokens_out * float(pout)) / 1_000_000)


def debit(db: Session, row: ProviderRegistry, amount_minor: int, *, now: datetime | None = None) -> bool:
    """Add a paid call's cost to this month's budget. Returns False when the cap is now reached
    (the provider is paused and the owner is told)."""
    now = now or datetime.now(UTC)
    b = budget(db, scope="PAID_PROVIDER", provider_code=row.code, now=now)
    if b is None:
        row.enabled = False
        return False
    b.spent_minor = min(b.cap_minor, b.spent_minor + max(0, amount_minor))
    if b.spent_minor >= b.cap_minor:
        row.enabled = False
        notify_owners(
            db,
            event_type="cost.cap_reached",
            severity="CRITICAL",
            title="A paid provider reached its monthly cap",
            body=f"{row.code} spent its cap of {b.cap_minor / 100:.2f} this month and is paused.",
            dedup_key=f"cost.cap_reached:{row.code}:{b.month}",
            link="/usage",
            now=now,
        )
        db.flush()
        return False
    db.flush()
    return True
