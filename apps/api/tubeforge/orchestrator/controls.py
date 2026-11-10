"""Emergency Stop and kill switches, checked inside running jobs (SYSTEM_ARCHITECTURE §10).

The transition engine refuses work while Emergency Stop is on; long jobs also call
:func:`stop_reason` at each checkpoint (e.g. between upload chunks) and stop there. The reconciler
re-enqueues them once the stop is cleared.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.db.models import KillSwitch, SystemSettings


def stop_reason(
    db: Session,
    *,
    channel_id: uuid.UUID | None = None,
    agent_code: str | None = None,
    provider_code: str | None = None,
) -> str | None:
    """Why work must stop now, or None. Reads committed state (call after commit / in a fresh TX)."""
    settings = db.get(SystemSettings, 1, populate_existing=True)
    if settings is None or settings.emergency_stop:
        return "EMERGENCY_STOP"
    targets: list[tuple[str, str]] = []
    if channel_id is not None:
        targets.append(("CHANNEL", str(channel_id)))
    if agent_code is not None:
        targets.append(("AGENT", agent_code))
    if provider_code is not None:
        targets.append(("PROVIDER", provider_code))
    for scope, target in targets:
        hit = db.scalar(
            select(KillSwitch.id).where(
                KillSwitch.active.is_(True), KillSwitch.scope == scope, KillSwitch.target_id == target
            )
        )
        if hit is not None:
            return f"KILL_SWITCH_{scope}"
    return None
