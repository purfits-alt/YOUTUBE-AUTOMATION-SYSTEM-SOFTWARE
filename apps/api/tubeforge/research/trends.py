"""Google Trends API (alpha) — off by default (CHANNEL_DISCOVERY_SPEC §1 ``TRENDS_API_ALPHA``).

The Trends API is an invitation-only alpha. TubeForge does not scrape Google Trends. Until the
owner has been accepted into the alpha **and** approves and enables the source, every call is
refused. The request format is added only once access exists and its terms have been read.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from tubeforge.research.sources import SourceUnavailableError, get_source, require_usable

CODE = "TRENDS_API_ALPHA"


def interest_over_time(db: Session, keyword: str) -> None:
    require_usable(db, get_source(db, CODE))
    raise SourceUnavailableError(
        "NOT_AVAILABLE",
        "The Google Trends API (alpha) adapter is added once the owner has been accepted into the alpha.",
    )
