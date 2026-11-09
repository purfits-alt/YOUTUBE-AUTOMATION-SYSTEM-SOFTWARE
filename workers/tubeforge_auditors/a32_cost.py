"""A32 — Free-Tier Cost & Usage Monitor (AI_AGENT_ARCHITECTURE A32, COST_CONTROL_SPEC §5–§6).

Deterministic. Every run (``a32.usage_scan``, every 15 min):
- each provider limit (GLOBAL) and each paid budget against its use → alerts at 70 / 90 / 100 %
  (one alert per threshold, metric and period);
- the YouTube quota buckets → the same thresholds;
- providers whose facts were verified more than 90 days ago → a re-verify reminder;
- on the 1st of each month → "confirm no charges appeared on your Google Cloud billing" reminder.
Paid-tier signs in provider responses are handled live by the gateway (``gateway/indicators.py``).
Each run is logged in ``agent_runs`` with the report as output.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import AgentRun, CostBudget, OAuthClient, ProviderRegistry, UsageLimit
from tubeforge.gateway import limits, paid
from tubeforge.notifications import notify_owners
from tubeforge.youtube import quota

CODE = "A32_COST_MONITOR"
THRESHOLDS = ((100, "CRITICAL"), (90, "WARNING"), (70, "INFO"))
REVERIFY_AFTER = timedelta(days=90)
# Keys already contain the period (day / month), so a long window means "once per period".
DEDUP = timedelta(days=32)


@dataclass
class Line:
    subject: str
    metric: str
    period: str
    used: int
    limit: int
    pct: int


@dataclass
class UsageReport:
    generated_at: str
    lines: list[Line] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    reverify_due: list[str] = field(default_factory=list)
    paid_enabled: list[str] = field(default_factory=list)
    spent_minor_this_month: int = 0


def _alert(db: Session, report: UsageReport, line: Line, key: str, now: datetime) -> None:
    for threshold, severity in THRESHOLDS:
        if line.pct >= threshold:
            notify_owners(
                db,
                event_type="usage.alert",
                severity=severity,
                title=f"{line.subject}: {line.pct}% of its {line.period.lower()} {line.metric.lower()} used",
                body=f"{line.used:,} of {line.limit:,}. "
                + (
                    "Tasks that need it now wait or use the next provider."
                    if threshold == 100
                    else "Plan accordingly."
                ),
                dedup_key=f"usage.alert:{line.subject}:{line.metric}:{key}:{threshold}",
                dedup_window=DEDUP,
                link="/usage",
                now=now,
            )
            report.alerts.append(f"{line.subject} {line.metric} {threshold}%")
            return


def scan(db: Session, *, now: datetime | None = None) -> UsageReport:
    now = now or datetime.now(UTC)
    report = UsageReport(generated_at=now.isoformat())
    for lim in db.scalars(select(UsageLimit).where(UsageLimit.scope == "GLOBAL")):
        key = limits.period_key(lim.period, lim.reset_tz, now)
        used = limits.used(db, lim.provider_code, lim.metric, key)
        line = Line(
            lim.provider_code,
            lim.metric,
            lim.period,
            used,
            int(lim.limit_value),
            _pct(used, int(lim.limit_value)),
        )
        report.lines.append(line)
        _alert(db, report, line, key, now)

    projects = {c.gcp_project_id for c in db.scalars(select(OAuthClient)) if c.gcp_project_id} or {
        quota.DEFAULT_PROJECT
    }
    for project in sorted(projects):
        for b in quota.status(db, project, now=now):
            spent = b.used + b.held
            line = Line(
                f"YouTube {b.bucket} ({project})", "UNITS", "DAY", spent, b.usable, _pct(spent, b.usable)
            )
            report.lines.append(line)
            _alert(db, report, line, quota.pt_day(now).isoformat(), now)

    month = paid.month_key(now)
    for budget in db.scalars(select(CostBudget).where(CostBudget.month == month)):
        report.spent_minor_this_month += budget.spent_minor
        if budget.cap_minor > 0:
            subject = f"Budget {budget.scope}{':' + budget.provider_code if budget.provider_code else ''}"
            line = Line(
                subject,
                "MONEY_MINOR",
                "MONTH",
                budget.spent_minor,
                budget.cap_minor,
                _pct(budget.spent_minor, budget.cap_minor),
            )
            report.lines.append(line)
            _alert(db, report, line, month, now)

    today = now.date()
    for provider in db.scalars(select(ProviderRegistry)):
        if provider.tier == "P" and provider.enabled:
            report.paid_enabled.append(provider.code)
        if provider.verified_at + REVERIFY_AFTER <= today:
            report.reverify_due.append(provider.code)
    if report.reverify_due:
        notify_owners(
            db,
            event_type="provider.reverify",
            severity="INFO",
            title="Provider facts are due for a re-check",
            body="Verified more than 90 days ago: " + ", ".join(report.reverify_due[:10]),
            dedup_key=f"provider.reverify:{month}",
            dedup_window=DEDUP,
            link="/usage",
            now=now,
        )
    if today.day == 1:
        notify_owners(
            db,
            event_type="cost.statement_check",
            severity="INFO",
            title="Monthly check: no charges expected",
            body="Open Google Cloud billing for your TubeForge projects and confirm there is no "
            "billing account and no charge. TubeForge is designed to cost nothing.",
            dedup_key=f"cost.statement_check:{month}",
            dedup_window=DEDUP,
            link="/usage",
            now=now,
        )
    _log_run(db, report, now)
    db.commit()
    return report


def _pct(used: int, limit: int) -> int:
    return 100 if limit <= 0 else min(999, round(used * 100 / limit))


def _log_run(db: Session, report: UsageReport, now: datetime) -> None:
    data: dict[str, Any] = asdict(report)
    db.add(
        AgentRun(
            id=uuid7(),
            agent_code=CODE,
            input_sha256=hashlib.sha256(f"{CODE}:{now.isoformat()}".encode()).hexdigest(),
            input={"trigger": "periodic", "at": now.isoformat()},
            output=data,
            status="SUCCEEDED",
            duration_ms=0,
            started_at=now,
            finished_at=now,
        )
    )
