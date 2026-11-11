"""Owner-approved RSS/Atom feeds (CHANNEL_DISCOVERY_SPEC §1 ``RSS:<slug>``).

The feed URL is fetched through the research fetcher, parsed without DTDs, and every item is
stored as its own source document (title, date and a plain-text summary), so an evidence quote
can point at the exact item. Item links are kept as references and are never fetched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from tubeforge.db.models import ResearchSource
from tubeforge.research.fetcher import FEED_TYPES, ResearchFetcher
from tubeforge.research.sanitize import FeedItem, parse_feed
from tubeforge.research.sources import SourceUnavailableError, require_usable, store_document


@dataclass(frozen=True)
class FeedResult:
    title: str | None
    items: list[tuple[FeedItem, str]]  # (item, source_document id)


def read_feed(db: Session, fetcher: ResearchFetcher, source: ResearchSource) -> FeedResult:
    if source.kind != "RSS" or not source.base_url:
        raise SourceUnavailableError("NOT_FETCHABLE", f"{source.code} is not a feed.")
    require_usable(db, source)
    fetched = fetcher.get(source.base_url, source.allowed_hosts, accept=FEED_TYPES)
    title, items = parse_feed(fetched.body)
    stored: list[tuple[FeedItem, str]] = []
    for item in items:
        link = item.link if item.link and item.link.startswith(("https://", "http://")) else None
        ref = link or f"{fetched.url}#item-{hashlib.sha256(item.title.encode()).hexdigest()[:12]}"
        text = "\n".join(x for x in (item.title, item.published or "", "", item.summary) if x is not None)
        doc = store_document(db, source, url=ref, title=item.title, text=text)
        stored.append((item, str(doc.id)))
    return FeedResult(title, stored)
