"""Maintenance jobs (BACKEND_SPECIFICATION §5, queue ``maintenance``)."""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from tubeforge.config import get_settings
from tubeforge.db.session import get_engine
from tubeforge.logging import get_logger
from tubeforge.secrets import SecretBox, default_store
from tubeforge.youtube import oauth

# Daily 02:00 UTC = 07:00 PKT (Procrastinate evaluates cron in UTC).
OAUTH_HEALTH_CRON = "0 2 * * *"


def token_health(timestamp: int) -> dict[str, int]:
    """mnt.token_health: refresh every active YouTube token; warn before Testing-mode expiry."""
    settings = get_settings()
    google = oauth.GoogleOAuth()
    try:
        with Session(get_engine(settings.database_url)) as db:
            result = oauth.token_health(db, SecretBox(default_store(settings.env)), google)
            db.commit()
    finally:
        google.close()
    get_logger("tubeforge.jobs").info("mnt.token_health", scheduled_at=timestamp, **asdict(result))
    return asdict(result)
