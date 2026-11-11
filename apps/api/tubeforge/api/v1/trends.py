"""Trends and keywords per channel (BACKEND_SPECIFICATION §4.5, CHANNEL_DISCOVERY_SPEC §5–§6).

Trend items come from the daily A03 scan (or "Scan now"); their strength is computed in code.
Expired items are shown as EXPIRED and never offered as ideas. Turning a trend into an idea needs
the idea pipeline (Phase 7), so that command says so instead of pretending.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.v1.channels import get_channel
from tubeforge.audit import record
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Keyword, SourceDocument, TrendItem
from tubeforge.orchestrator.controls import stop_reason
from tubeforge.queue import defer_in_transaction
from tubeforge.research.forbidden import scan

router = APIRouter(tags=["research"])
View = Annotated[Principal, Depends(require("research.view"))]
Run = Annotated[Principal, Depends(require("research.run"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("STOPPED / NOT_AVAILABLE_YET / DUPLICATE_KEYWORD / NOT_ACTIVE"),
    422: problem_doc("FORBIDDEN_PHRASE / IDEMPOTENCY_MISMATCH"),
}
Phrase = Annotated[str, Field(min_length=2, max_length=80, pattern=r"^[^\x00-\x1f<>]+$")]


class SourceRef(BaseModel):
    id: uuid.UUID
    url: str
    title: str | None


class TrendOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID | None
    topic: str
    summary: str
    signal_strength: Decimal
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    detected_at: datetime
    expires_at: datetime
    status: Literal["ACTIVE", "USED", "DISMISSED", "EXPIRED"]
    sources: list[SourceRef]


class ScanIn(BaseModel):
    channel_id: uuid.UUID


class QueuedOut(BaseModel):
    job_id: int
    status: Literal["QUEUED"] = "QUEUED"


class KeywordOut(BaseModel):
    id: uuid.UUID
    phrase: str
    language: str
    notes: str | None
    evidence: list[dict[str, Any]]
    created_at: datetime


class KeywordIn(BaseModel):
    phrase: Phrase | None = None
    seeds: list[Phrase] | None = Field(default=None, max_length=10)


def _audit(request: Request, db: Db, p: Principal, action: str, kind: str, ref: uuid.UUID, **d: Any) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type=kind,
        entity_id=str(ref),
        details=d or None,
        request_id=request_id(request),
        ip=client_ip(request),
    )


def _trend_out(db: Db, row: TrendItem, now: datetime) -> TrendOut:
    docs = db.scalars(select(SourceDocument).where(SourceDocument.id.in_(row.source_document_ids))).all()
    status = "EXPIRED" if row.status == "ACTIVE" and row.expires_at <= now else row.status
    return TrendOut(
        id=row.id,
        channel_id=row.channel_id,
        topic=row.topic,
        summary=row.summary,
        signal_strength=row.signal_strength,
        confidence=row.confidence,
        detected_at=row.detected_at,
        expires_at=row.expires_at,
        status=status,
        sources=[SourceRef(id=d.id, url=d.url, title=d.title) for d in docs],
    )


@router.get("/trends", response_model=list[TrendOut])
def list_trends(
    db: Db,
    p: View,
    channel_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[TrendOut]:
    now = datetime.now(UTC)
    stmt = select(TrendItem).order_by(TrendItem.signal_strength.desc(), TrendItem.detected_at.desc())
    if channel_id is not None:
        stmt = stmt.where(TrendItem.channel_id == channel_id)
    if not include_inactive:
        stmt = stmt.where(TrendItem.status == "ACTIVE", TrendItem.expires_at > now)
    return [_trend_out(db, r, now) for r in db.scalars(stmt.limit(limit))]


@router.post("/trends/scan", response_model=QueuedOut, status_code=202, responses=WRITE)
def scan_now(body: ScanIn, request: Request, db: Db, p: Run) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, body.channel_id)
    if stop_reason(db, channel_id=body.channel_id) is not None:
        raise ProblemError(
            409, "STOPPED", "Stopped", "Emergency Stop or a kill switch is on for this channel."
        )
    job = defer_in_transaction(
        db, "research.trend_scan", queue="agents", args={"channel_id": str(body.channel_id)}
    )
    _audit(request, db, p, "trends.scan_requested", "channel", body.channel_id)
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post("/trends/{trend_id}/commands/{cmd}", response_model=TrendOut, responses=WRITE)
def trend_command(
    trend_id: uuid.UUID, cmd: Literal["dismiss", "to-idea"], request: Request, db: Db, p: Run
) -> TrendOut:
    row = db.get(TrendItem, trend_id, with_for_update=True)
    if row is None:
        raise not_found("No such trend.")
    if cmd == "to-idea":
        raise ProblemError(
            409,
            "NOT_AVAILABLE_YET",
            "Coming in Phase 7",
            "Turning a trend into an idea arrives with Ideas (Phase 7).",
        )
    if row.status != "ACTIVE":
        raise ProblemError(409, "NOT_ACTIVE", "Not active", "Only an active trend can be dismissed.")
    row.status = "DISMISSED"
    _audit(request, db, p, "trend.dismissed", "trend_item", row.id, topic=row.topic)
    db.commit()
    return _trend_out(db, row, datetime.now(UTC))


# -------------------------------------------------------------------------------------- keywords
@router.get("/channels/{channel_id}/keywords", response_model=list[KeywordOut])
def list_keywords(channel_id: uuid.UUID, db: Db, p: View) -> list[KeywordOut]:
    get_channel(db, channel_id)
    rows = db.scalars(select(Keyword).where(Keyword.channel_id == channel_id).order_by(Keyword.phrase))
    return [KeywordOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/channels/{channel_id}/keywords", responses=WRITE)
def add_keywords(
    channel_id: uuid.UUID, body: KeywordIn, request: Request, response: Response, db: Db, p: Run
) -> Any:
    """``{phrase}`` adds one phrase now; ``{seeds}`` asks A05 for suggestions (queued job)."""
    channel = get_channel(db, channel_id)
    if (body.phrase is None) == (body.seeds is None):
        raise ProblemError(422, "VALIDATION_ERROR", "Invalid request", "Send either phrase or seeds.")
    if body.seeds is not None:
        idem = Idempotency(db, request, p.user.id, body)
        if (replayed := idem.replay()) is not None:
            return replayed
        if stop_reason(db, channel_id=channel_id) is not None:
            raise ProblemError(
                409, "STOPPED", "Stopped", "Emergency Stop or a kill switch is on for this channel."
            )
        job = defer_in_transaction(
            db, "research.keywords", queue="agents", args={"channel_id": str(channel_id), "seeds": body.seeds}
        )
        out: Any = QueuedOut(job_id=job)
        idem.store(202, out.model_dump(mode="json"))
        response.status_code = 202
    else:
        phrase = " ".join(str(body.phrase).split())
        if scan(phrase):
            raise ProblemError(422, "FORBIDDEN_PHRASE", "Not allowed", "That phrase makes a promise.")
        row = Keyword(id=uuid7(), channel_id=channel.id, phrase=phrase, language=channel.content_language,
                      evidence=[], notes="Added by the owner")  # fmt: skip
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ProblemError(
                409, "DUPLICATE_KEYWORD", "Already listed", "That phrase is already listed."
            ) from exc
        db.refresh(row)
        out = KeywordOut.model_validate(row, from_attributes=True)
        response.status_code = 201
    _audit(request, db, p, "keywords.added", "channel", channel_id, seeds=body.seeds, phrase=body.phrase)
    db.commit()
    return out


@router.delete("/channels/{channel_id}/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    channel_id: uuid.UUID, keyword_id: uuid.UUID, request: Request, db: Db, p: Run
) -> Response:
    row = db.get(Keyword, keyword_id)
    if row is None or row.channel_id != channel_id:
        raise not_found("No such keyword.")
    db.delete(row)
    _audit(request, db, p, "keywords.deleted", "channel", channel_id, phrase=row.phrase)
    db.commit()
    return Response(status_code=204)
