"""Research source registry (BACKEND_SPECIFICATION §4.5 ``/research-sources``, CHANNEL_DISCOVERY_SPEC §1).

The owner sees every source with its approval state, adds RSS feeds and web hosts (they start off
and unapproved), switches sources on and off, records that the terms were checked, and runs one
test fetch. Switching on a source that still needs approval asks for the password again.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require, require_recent_reauth
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.audit import record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import ResearchSource, SourceDocument
from tubeforge.research import rss, trends, wikipedia
from tubeforge.research.fetcher import FetchError, ResearchFetcher
from tubeforge.research.net import FetchBlockedError, check_url
from tubeforge.research.sanitize import FeedError
from tubeforge.research.sources import FETCHABLE_KINDS, SLUG, SourceUnavailableError, fetch_web_page

router = APIRouter(tags=["research"])
View = Annotated[Principal, Depends(require("research.view"))]
Run = Annotated[Principal, Depends(require("research.run"))]
Manage = Annotated[Principal, Depends(require("settings.manage"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc(
        "DUPLICATE_SOURCE / SOURCE_BLOCKED / STOPPED / NOT_APPROVED / SOURCE_OFF / NOT_FETCHABLE"
    ),
    422: problem_doc("FETCH_BLOCKED / INVALID_URL"),
    502: problem_doc("FETCH_FAILED / FEED_UNREADABLE"),
}


class SourceOut(BaseModel):
    id: uuid.UUID
    code: str
    kind: Literal["API", "RSS", "OWNER", "OWN_ANALYTICS", "WEB_ALLOWLISTED"]
    base_url: str | None
    allowed_hosts: list[str]
    terms_url: str | None
    terms_verified_at: date | None
    approval_status: Literal["APPROVED", "REQUIRES_OWNER_APPROVAL", "BLOCKED"]
    enabled: bool
    fetchable: bool
    documents: int


class SourceIn(BaseModel):
    kind: Literal["RSS", "WEB_ALLOWLISTED"]
    slug: str = Field(pattern=SLUG.pattern, description="Short name: lower-case letters, digits and '-'.")
    url: str = Field(min_length=12, max_length=2000)
    terms_url: str | None = Field(default=None, pattern=r"^https://\S{3,490}$")


class SourcePatch(BaseModel):
    enabled: bool | None = None
    terms_verified: Literal[True] | None = Field(
        default=None, description="The owner checked the terms today."
    )


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str | None
    url: str
    fetched_at: datetime
    expires_at: datetime
    excerpt: str


class TestFetchOut(BaseModel):
    documents_stored: int
    samples: list[DocumentOut]


def _out(db: Session, row: ResearchSource) -> SourceOut:
    n = db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.source_id == row.id))
    return SourceOut(
        id=row.id,
        code=row.code,
        kind=row.kind,
        base_url=row.base_url,
        allowed_hosts=list(row.allowed_hosts or []),
        terms_url=row.terms_url,
        terms_verified_at=row.terms_verified_at,
        approval_status=row.approval_status,
        enabled=row.enabled,
        fetchable=row.kind in FETCHABLE_KINDS,
        documents=int(n or 0),
    )


def _doc_out(doc: SourceDocument) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        url=doc.url,
        fetched_at=doc.fetched_at,
        expires_at=doc.expires_at,
        excerpt=doc.content_text[:300],
    )


def _source(db: Session, source_id: uuid.UUID, *, lock: bool = False) -> ResearchSource:
    row = db.get(ResearchSource, source_id, with_for_update=lock)
    if row is None:
        raise not_found("No such research source.")
    return row


def _audit(
    request: Request, db: Session, p: Principal, action: str, row: ResearchSource, **details: Any
) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="research_source",
        entity_id=str(row.id),
        details={"code": row.code, **details},
        request_id=request_id(request),
        ip=client_ip(request),
    )


@router.get("/research-sources", response_model=list[SourceOut])
def list_sources(db: Db, p: View) -> list[SourceOut]:
    rows = db.scalars(select(ResearchSource).order_by(ResearchSource.kind, ResearchSource.code)).all()
    return [_out(db, r) for r in rows]


@router.post("/research-sources", response_model=SourceOut, status_code=201, responses=WRITE)
def add_source(body: SourceIn, request: Request, db: Db, p: Manage) -> SourceOut:
    try:
        host = httpx.URL(body.url).host.lower().rstrip(".")
        checked = check_url(body.url, [host])
    except FetchBlockedError as exc:
        raise ProblemError(422, "INVALID_URL", "Address not allowed", str(exc)) from exc
    prefix = "RSS" if body.kind == "RSS" else "WEB"
    row = ResearchSource(
        id=uuid7(),
        code=f"{prefix}:{body.slug}",
        kind=body.kind,
        base_url=checked.url,
        allowed_hosts=[checked.host],
        terms_url=body.terms_url,
        approval_status="REQUIRES_OWNER_APPROVAL",
        enabled=False,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ProblemError(409, "DUPLICATE_SOURCE", "Already added", f"{row.code} exists already.") from exc
    _audit(request, db, p, "research_source.added", row, url=checked.url, host=checked.host)
    db.commit()
    return _out(db, row)


@router.patch("/research-sources/{source_id}", response_model=SourceOut, responses=WRITE)
def patch_source(source_id: uuid.UUID, body: SourcePatch, request: Request, db: Db, p: Manage) -> SourceOut:
    row = _source(db, source_id, lock=True)
    if body.enabled is True and not row.enabled:
        if row.approval_status == "BLOCKED":
            raise ProblemError(409, "SOURCE_BLOCKED", "Blocked", f"{row.code} is blocked and cannot be used.")
        if row.approval_status == "REQUIRES_OWNER_APPROVAL":
            require_recent_reauth(p)
            row.approval_status = "APPROVED"
            security_event(
                db, "RESEARCH_SOURCE_APPROVED", "INFO", user_id=p.user.id, details={"code": row.code}
            )
        row.enabled = True
        _audit(request, db, p, "research_source.enabled", row, approval=row.approval_status)
    elif body.enabled is False and row.enabled:
        row.enabled = False
        _audit(request, db, p, "research_source.disabled", row)
    if body.terms_verified:
        row.terms_verified_at = datetime.now(UTC).date()
        _audit(request, db, p, "research_source.terms_verified", row, terms_url=row.terms_url)
    db.commit()
    return _out(db, row)


def _fetcher(request: Request) -> ResearchFetcher:
    factory = getattr(request.app.state, "research_fetcher_factory", None)
    return factory() if factory is not None else ResearchFetcher()


@router.post("/research-sources/{source_id}/test", response_model=TestFetchOut, responses=WRITE)
def test_fetch(source_id: uuid.UUID, request: Request, db: Db, p: Run) -> TestFetchOut:
    """Fetch the source once now and store what came back (a quick check that it works)."""
    row = _source(db, source_id)
    try:
        with _fetcher(request) as fetcher:
            if row.code == wikipedia.CODE:
                end = datetime.now(UTC).date() - timedelta(days=1)
                series = wikipedia.WikipediaPageviews(db, fetcher).per_article(
                    "en.wikipedia", "Main_Page", end - timedelta(days=6), end
                )
                ids = [series.document_id]
            elif row.code == trends.CODE:
                trends.interest_over_time(db, "test")
                ids = []
            elif row.kind == "RSS":
                ids = [doc_id for _item, doc_id in rss.read_feed(db, fetcher, row).items]
            elif row.kind == "WEB_ALLOWLISTED" and row.base_url:
                ids = [str(fetch_web_page(db, fetcher, row, row.base_url).id)]
            else:
                raise SourceUnavailableError("NOT_FETCHABLE", f"{row.code} is not fetched from the web.")
    except SourceUnavailableError as exc:
        raise ProblemError(409, exc.code, "Source not available", exc.message) from exc
    except FetchBlockedError as exc:
        raise ProblemError(422, "FETCH_BLOCKED", "Blocked by the outbound rules", str(exc)) from exc
    except FeedError as exc:
        raise ProblemError(502, "FEED_UNREADABLE", "Feed could not be read", str(exc)) from exc
    except (FetchError, ValueError) as exc:
        raise ProblemError(502, "FETCH_FAILED", "Fetch failed", str(exc)) from exc
    _audit(request, db, p, "research_source.test_fetch", row, documents=len(ids))
    db.commit()
    docs = db.scalars(select(SourceDocument).where(SourceDocument.id.in_([uuid.UUID(i) for i in ids[:5]])))
    return TestFetchOut(documents_stored=len(ids), samples=[_doc_out(d) for d in docs])


@router.get("/research-sources/{source_id}/documents", response_model=list[DocumentOut])
def list_documents(
    source_id: uuid.UUID, db: Db, p: View, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[DocumentOut]:
    _source(db, source_id)
    docs = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.source_id == source_id)
        .order_by(SourceDocument.fetched_at.desc())
        .limit(limit)
    ).all()
    return [_doc_out(d) for d in docs]
