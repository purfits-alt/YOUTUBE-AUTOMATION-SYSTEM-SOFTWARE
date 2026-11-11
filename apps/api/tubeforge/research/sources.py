"""Source registry rules and document storage (CHANNEL_DISCOVERY_SPEC §1, DATABASE_SCHEMA §3).

A source can be fetched only when it is enabled, approved and Emergency Stop is off. Owner-added
feeds and web hosts start as ``REQUIRES_OWNER_APPROVAL`` and switched off; switching one on needs
a fresh password check (API). Documents are stored as sanitised plain text and expire after 90 days.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import ResearchSource, SourceDocument
from tubeforge.orchestrator.controls import stop_reason
from tubeforge.research.fetcher import HTML_TYPES, ResearchFetcher
from tubeforge.research.sanitize import clean_text, html_to_text

DOC_TTL = timedelta(days=90)
FETCHABLE_KINDS = ("API", "RSS", "WEB_ALLOWLISTED")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class SourceUnavailableError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def get_source(db: Session, code: str) -> ResearchSource:
    row = db.scalar(select(ResearchSource).where(ResearchSource.code == code))
    if row is None:
        raise SourceUnavailableError("UNKNOWN_SOURCE", f"No research source '{code}'.")
    return row


def require_usable(db: Session, source: ResearchSource) -> None:
    if stop_reason(db) is not None:
        raise SourceUnavailableError("STOPPED", "Emergency Stop is on: nothing is fetched.")
    if source.kind not in FETCHABLE_KINDS:
        raise SourceUnavailableError("NOT_FETCHABLE", f"{source.code} is not fetched from the web.")
    if source.approval_status != "APPROVED":
        raise SourceUnavailableError("NOT_APPROVED", f"{source.code} is waiting for the owner's approval.")
    if not source.enabled:
        raise SourceUnavailableError("SOURCE_OFF", f"{source.code} is switched off.")


def store_document(
    db: Session,
    source: ResearchSource,
    *,
    url: str,
    title: str | None,
    text: str,
    language: str | None = None,
    now: datetime | None = None,
) -> SourceDocument:
    """Insert, or refresh the expiry of the identical document (same URL and content)."""
    now = now or datetime.now(UTC)
    body = clean_text(text)
    sha = hashlib.sha256(body.encode()).hexdigest()
    db.execute(
        insert(SourceDocument)
        .values(
            id=uuid7(),
            source_id=source.id,
            url=url[:2000],
            title=(title or None) and clean_text(title, 500),
            fetched_at=now,
            content_sha256=sha,
            content_text=body,
            language=language,
            expires_at=now + DOC_TTL,
        )
        .on_conflict_do_update(
            index_elements=["url", "content_sha256"],
            set_={"fetched_at": now, "expires_at": now + DOC_TTL},
        )
    )
    doc = db.scalar(
        select(SourceDocument)
        .where(SourceDocument.url == url[:2000], SourceDocument.content_sha256 == sha)
        .execution_options(populate_existing=True)
    )
    assert doc is not None
    return doc


def fetch_web_page(db: Session, fetcher: ResearchFetcher, source: ResearchSource, url: str) -> SourceDocument:
    """One page of an owner-approved web host → a stored plain-text document."""
    require_usable(db, source)
    page = fetcher.get(url, source.allowed_hosts, accept=HTML_TYPES)
    title, text = html_to_text(page.text())
    return store_document(db, source, url=page.url, title=title, text=text)


def purge_expired(db: Session, *, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    result = db.execute(delete(SourceDocument).where(SourceDocument.expires_at < now))
    db.flush()
    return int(getattr(result, "rowcount", 0) or 0)
