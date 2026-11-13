"""Niche discovery and blueprints (BACKEND_SPECIFICATION §4.5, CHANNEL_DISCOVERY_SPEC §2–§4).

Starting a discovery or a blueprint queues a worker job (fetching and model calls never run in the
API). Scores are computed in code; ``/niches/rescore`` recomputes them for new weights without any
model call. Every candidate response carries the fixed footer and the confidence band.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.audit import record
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    ChannelPublishingRules,
    ChannelStrategy,
    NicheCandidate,
    NicheReport,
    ScoreWeightProfile,
)
from tubeforge.orchestrator.controls import stop_reason
from tubeforge.queue import defer_in_transaction
from tubeforge.research import blueprint as bp
from tubeforge.research.niches import criteria_only, profile_weights, rescore, side_records
from tubeforge.research.scoring import CRITERIA, FOOTER, MAX_WEIGHT, check_weights, remarks, score

router = APIRouter(tags=["research"])
View = Annotated[Principal, Depends(require("research.view"))]
Run = Annotated[Principal, Depends(require("research.run"))]
StrategyView = Annotated[Principal, Depends(require("strategy.view"))]
StrategyManage = Annotated[Principal, Depends(require("strategy.manage"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("STOPPED / NOT_SHORTLISTED / CANDIDATE_CONVERTED / DUPLICATE_PROFILE"),
    422: problem_doc("INVALID_WEIGHTS / IDEMPOTENCY_MISMATCH"),
}
Language = Literal["en", "es", "fr", "de", "ur"]
Confidence = Literal["LOW", "MEDIUM", "HIGH"]
Level = Literal["LOW", "MEDIUM", "HIGH"]
Term = Annotated[str, Field(min_length=2, max_length=80, pattern=r"^[^\x00-\x1f<>]+$")]


class ReportIn(BaseModel):
    languages: list[Language] = Field(default=["en"], min_length=1, max_length=5)
    interests: list[Term] = Field(default_factory=list, max_length=10)
    avoid: list[Term] = Field(default_factory=list, max_length=20)
    weight_profile_id: uuid.UUID | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    status: Literal["QUEUED", "RUNNING", "DONE", "FAILED", "WAITING_QUOTA", "STOPPED"]
    languages: list[str]
    interests: list[str]
    avoid: list[str]
    weight_profile_id: uuid.UUID | None
    documents: int | None
    candidates: int | None
    dropped: list[str]
    skipped: list[str]
    error: str | None
    created_at: datetime
    updated_at: datetime


class EvidenceOut(BaseModel):
    source_document_id: str
    url: str
    title: str | None
    quote: str


class CriterionOut(BaseModel):
    code: str
    value: int
    weight: float
    confidence: Confidence
    evidence: list[EvidenceOut]
    note: str | None


class RemarkOut(BaseModel):
    kind: Literal["STRENGTH", "WATCH"]
    code: str
    value: int
    confidence: Level


class CandidateOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    name: str
    summary: str
    language: str
    opportunity_score: Decimal
    band: Decimal | None
    criteria: list[CriterionOut]
    originality_angles: list[str]
    inauthentic_risk: Level
    production_difficulty: Level
    status: Literal["NEW", "SHORTLISTED", "DISMISSED", "CONVERTED"]
    remarks: list[RemarkOut] = Field(default_factory=list)
    footer: str = FOOTER


class ReportDetail(ReportOut):
    candidates_list: list[CandidateOut]


class RescoreIn(BaseModel):
    report_id: uuid.UUID
    weights: dict[str, float] | None = None
    weight_profile_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one(self) -> RescoreIn:
        if (self.weights is None) == (self.weight_profile_id is None):
            raise ValueError("Give either weights or weight_profile_id.")
        return self


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    weights: dict[str, float]
    is_default: bool = False


class ProfilePut(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    weights: dict[str, float] | None = None
    is_default: Literal[True] | None = None


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    weights: dict[str, float]
    is_default: bool
    max_weight: float = MAX_WEIGHT


STRATEGY_WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("NOT_EDITABLE / INVALID_TRANSITION / BLUEPRINT_HAS_PROBLEMS"),
    412: problem_doc("VERSION_CONFLICT"),
    422: problem_doc("BLUEPRINT_INVALID / CHANNEL_NAME_REQUIRED"),
    428: problem_doc("IF_MATCH_REQUIRED"),
}


class StrategyIn(BaseModel):
    niche_candidate_id: uuid.UUID
    owner_notes: str = Field(default="", max_length=2000)


class QueuedOut(BaseModel):
    job_id: int
    status: Literal["QUEUED"] = "QUEUED"


class StrategyOut(BaseModel):
    id: uuid.UUID
    niche_candidate_id: uuid.UUID | None
    channel_id: uuid.UUID | None
    version: int
    status: Literal["DRAFT", "PROPOSED", "APPROVED", "SUPERSEDED", "REJECTED"]
    blueprint: dict[str, Any]
    problems: list[str]
    approved_at: datetime | None
    created_at: datetime
    etag: str


class StrategyPatch(BaseModel):
    blueprint: dict[str, Any]


class ApproveIn(BaseModel):
    channel_name: str = Field(min_length=1, max_length=80)
    is_test_channel: bool = Field(
        default=True, description="Start as the test channel (private uploads only)."
    )


# --------------------------------------------------------------------------------------- helpers
def _report_out(row: NicheReport) -> dict[str, Any]:
    p, r = row.params, row.params.get("result", {})
    return {
        "id": row.id,
        "status": row.status,
        "languages": p.get("languages", []),
        "interests": p.get("interests", []),
        "avoid": p.get("avoid", []),
        "weight_profile_id": p.get("weight_profile_id"),
        "documents": r.get("documents"),
        "candidates": r.get("candidates"),
        "dropped": r.get("dropped", []),
        "skipped": r.get("skipped", []),
        "error": r.get("error"),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _candidate_out(row: NicheCandidate, weights: dict[str, float] | None = None) -> CandidateOut:
    crit = criteria_only(row.criteria)
    w = weights or {c["code"]: float(c.get("weight", CRITERIA.get(c["code"], 0))) for c in crit}
    s = score(crit, w)
    angles: list[str] = next(
        (c.get("angles", []) for c in side_records(row.criteria) if c["code"] == "_ORIGINALITY_ANGLES"), []
    )
    return CandidateOut(
        id=row.id,
        report_id=row.report_id,
        name=row.name,
        summary=row.summary,
        language=row.language,
        opportunity_score=row.opportunity_score,
        band=s.band,
        criteria=[
            CriterionOut(
                code=c["code"],
                value=int(c["value"]),
                weight=float(c.get("weight", w.get(c["code"], 0))),
                confidence=c["confidence"],
                evidence=[EvidenceOut(**e) for e in c.get("evidence", [])],
                note=c.get("note"),
            )
            for c in crit
        ],
        originality_angles=[str(a) for a in angles],
        inauthentic_risk=row.inauthentic_risk,
        production_difficulty=row.production_difficulty,
        status=row.status,
        remarks=[RemarkOut(**r) for r in remarks(crit, w)],
    )


def _audit(
    request: Request, db: Session, p: Principal, action: str, kind: str, ref: uuid.UUID, **d: Any
) -> None:
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


def _stopped(what: str) -> ProblemError:
    return ProblemError(409, "STOPPED", "Emergency Stop is on", f"Clear Emergency Stop to {what}.")


def _duplicate() -> ProblemError:
    return ProblemError(409, "DUPLICATE_PROFILE", "Name in use", "A profile with that name exists.")


def _weights_or_422(weights: dict[str, float]) -> dict[str, float]:
    try:
        return check_weights(weights)
    except ValueError as exc:
        raise ProblemError(422, "INVALID_WEIGHTS", "Invalid weights", str(exc)) from exc


def _profile_out(row: ScoreWeightProfile) -> ProfileOut:
    return ProfileOut(id=row.id, name=row.name, weights=check_weights(row.weights), is_default=row.is_default)


# ---------------------------------------------------------------------------------------- reports
@router.post("/niches/reports", response_model=ReportOut, status_code=202, responses=WRITE)
def start_report(body: ReportIn, request: Request, db: Db, p: Run) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    if stop_reason(db) is not None:
        raise ProblemError(
            409, "STOPPED", "Emergency Stop is on", "Clear Emergency Stop to start a discovery."
        )
    if body.weight_profile_id and db.get(ScoreWeightProfile, body.weight_profile_id) is None:
        raise not_found("No such weight profile.")
    row = NicheReport(
        id=uuid7(),
        requested_by=p.user.id,
        params={
            "languages": body.languages,
            "interests": body.interests,
            "avoid": body.avoid,
            "weight_profile_id": str(body.weight_profile_id) if body.weight_profile_id else None,
        },
        status="QUEUED",
    )
    db.add(row)
    db.flush()
    defer_in_transaction(db, "research.discover", queue="agents", args={"report_id": str(row.id)})
    _audit(request, db, p, "niche_report.started", "niche_report", row.id, languages=body.languages)
    db.refresh(row)
    out = ReportOut(**_report_out(row))
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/niches/reports", response_model=list[ReportOut])
def list_reports(db: Db, p: View, limit: Annotated[int, Query(ge=1, le=50)] = 20) -> list[ReportOut]:
    rows = db.scalars(select(NicheReport).order_by(NicheReport.created_at.desc()).limit(limit)).all()
    return [ReportOut(**_report_out(r)) for r in rows]


@router.get("/niches/reports/{report_id}", response_model=ReportDetail)
def get_report(report_id: uuid.UUID, db: Db, p: View) -> ReportDetail:
    row = db.get(NicheReport, report_id)
    if row is None:
        raise not_found("No such discovery report.")
    cands = db.scalars(
        select(NicheCandidate)
        .where(NicheCandidate.report_id == report_id)
        .order_by(NicheCandidate.opportunity_score.desc(), NicheCandidate.name)
    ).all()
    return ReportDetail(**_report_out(row), candidates_list=[_candidate_out(c) for c in cands])


@router.get("/niches/candidates/{candidate_id}", response_model=CandidateOut)
def get_candidate(candidate_id: uuid.UUID, db: Db, p: View) -> CandidateOut:
    row = db.get(NicheCandidate, candidate_id)
    if row is None:
        raise not_found("No such niche candidate.")
    return _candidate_out(row)


@router.post("/niches/candidates/{candidate_id}/commands/{cmd}", response_model=CandidateOut, responses=WRITE)
def candidate_command(
    candidate_id: uuid.UUID, cmd: Literal["shortlist", "dismiss"], request: Request, db: Db, p: Run
) -> CandidateOut:
    row = db.get(NicheCandidate, candidate_id, with_for_update=True)
    if row is None:
        raise not_found("No such niche candidate.")
    if row.status == "CONVERTED":
        raise ProblemError(
            409, "CANDIDATE_CONVERTED", "Already a channel", "This niche already became a channel."
        )
    row.status = "SHORTLISTED" if cmd == "shortlist" else "DISMISSED"
    _audit(request, db, p, f"niche_candidate.{cmd}", "niche_candidate", row.id, name=row.name)
    db.commit()
    return _candidate_out(row)


@router.post("/niches/rescore", response_model=list[CandidateOut], responses=WRITE)
def rescore_report(body: RescoreIn, request: Request, db: Db, p: Run) -> list[CandidateOut]:
    """Recompute every candidate's score for new weights — in code, no model call (§2)."""
    if db.get(NicheReport, body.report_id) is None:
        raise not_found("No such discovery report.")
    weights = (
        _weights_or_422(body.weights)
        if body.weights is not None
        else profile_weights(db, body.weight_profile_id)
    )
    rows = rescore(db, body.report_id, weights)
    _audit(request, db, p, "niche_report.rescored", "niche_report", body.report_id, weights=weights)
    db.commit()
    return [_candidate_out(r, weights) for r in rows]


# ------------------------------------------------------------------------------- weight profiles
@router.get("/niches/weight-profiles", response_model=list[ProfileOut])
def list_profiles(db: Db, p: View) -> list[ProfileOut]:
    rows = db.scalars(
        select(ScoreWeightProfile).order_by(ScoreWeightProfile.is_default.desc(), ScoreWeightProfile.name)
    )
    return [_profile_out(r) for r in rows]


def _make_default(db: Session, row: ScoreWeightProfile) -> None:
    for other in db.scalars(select(ScoreWeightProfile).where(ScoreWeightProfile.is_default)):
        other.is_default = False
    db.flush()
    row.is_default = True


@router.post("/niches/weight-profiles", response_model=ProfileOut, status_code=201, responses=WRITE)
def create_profile(body: ProfileIn, request: Request, db: Db, p: Run) -> ProfileOut:
    row = ScoreWeightProfile(id=uuid7(), name=body.name.strip(), weights=_weights_or_422(body.weights))
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ProblemError(
            409, "DUPLICATE_PROFILE", "Name in use", "A profile with that name exists."
        ) from exc
    if body.is_default:
        _make_default(db, row)
    _audit(request, db, p, "weight_profile.created", "weight_profile", row.id, name=row.name)
    db.commit()
    return _profile_out(row)


@router.put("/niches/weight-profiles/{profile_id}", response_model=ProfileOut, responses=WRITE)
def update_profile(profile_id: uuid.UUID, body: ProfilePut, request: Request, db: Db, p: Run) -> ProfileOut:
    row = db.get(ScoreWeightProfile, profile_id, with_for_update=True)
    if row is None:
        raise not_found("No such weight profile.")
    if body.name is not None:
        row.name = body.name.strip()
    if body.weights is not None:
        row.weights = _weights_or_422(body.weights)
    if body.is_default:
        _make_default(db, row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ProblemError(
            409, "DUPLICATE_PROFILE", "Name in use", "A profile with that name exists."
        ) from exc
    _audit(request, db, p, "weight_profile.updated", "weight_profile", row.id, name=row.name)
    db.commit()
    return _profile_out(row)


# ------------------------------------------------------------------------------------ blueprints
@router.post("/strategies", response_model=QueuedOut, status_code=202, responses=WRITE)
def start_blueprint(body: StrategyIn, request: Request, db: Db, p: StrategyManage) -> Any:
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    cand = db.get(NicheCandidate, body.niche_candidate_id)
    if cand is None:
        raise not_found("No such niche candidate.")
    if cand.status != "SHORTLISTED":
        raise ProblemError(
            409, "NOT_SHORTLISTED", "Shortlist first", "Shortlist this niche before its blueprint."
        )
    if stop_reason(db) is not None:
        raise ProblemError(
            409, "STOPPED", "Emergency Stop is on", "Clear Emergency Stop to generate a blueprint."
        )
    job = defer_in_transaction(
        db,
        "research.blueprint",
        queue="agents",
        args={"candidate_id": str(cand.id), "owner_notes": body.owner_notes},
    )
    _audit(request, db, p, "blueprint.requested", "niche_candidate", cand.id, name=cand.name)
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


def _etag(row: ChannelStrategy) -> str:
    raw = json.dumps({"s": row.status, "b": row.blueprint}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _strategy_out(row: ChannelStrategy) -> StrategyOut:
    return StrategyOut(
        id=row.id,
        niche_candidate_id=row.niche_candidate_id,
        channel_id=row.channel_id,
        version=row.version,
        status=row.status,
        blueprint=row.blueprint,
        problems=bp.problems(row.blueprint),
        approved_at=row.approved_at,
        created_at=row.created_at,
        etag=_etag(row),
    )


def _strategy(db: Session, strategy_id: uuid.UUID, *, lock: bool = False) -> ChannelStrategy:
    row = db.get(ChannelStrategy, strategy_id, with_for_update=lock)
    if row is None:
        raise not_found("No such blueprint.")
    return row


@router.get("/strategies", response_model=list[StrategyOut])
def list_strategies(
    db: Db, p: StrategyView, niche_candidate_id: uuid.UUID | None = None
) -> list[StrategyOut]:
    stmt = select(ChannelStrategy).order_by(ChannelStrategy.created_at.desc()).limit(50)
    if niche_candidate_id:
        stmt = stmt.where(ChannelStrategy.niche_candidate_id == niche_candidate_id)
    return [_strategy_out(r) for r in db.scalars(stmt)]


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: uuid.UUID, db: Db, p: StrategyView, response: Response) -> StrategyOut:
    out = _strategy_out(_strategy(db, strategy_id))
    response.headers["ETag"] = f'"{out.etag}"'
    return out


@router.patch("/strategies/{strategy_id}", response_model=StrategyOut, responses=STRATEGY_WRITE)
def edit_strategy(
    strategy_id: uuid.UUID,
    body: StrategyPatch,
    request: Request,
    db: Db,
    p: StrategyManage,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> StrategyOut:
    """The owner edits a DRAFT. The saved blueprint must always match the schema; other rule problems
    may remain while it is a draft (they block propose and approve)."""
    row = _strategy(db, strategy_id, lock=True)
    if if_match is None:
        raise ProblemError(
            428, "IF_MATCH_REQUIRED", "Version needed", "Send the blueprint's ETag in If-Match."
        )
    if if_match.strip().strip('"') != _etag(row):
        raise ProblemError(
            412, "VERSION_CONFLICT", "Changed elsewhere", "Reload the blueprint and try again."
        )
    if row.status != "DRAFT":
        raise ProblemError(
            409, "NOT_EDITABLE", "Not a draft", "Only a draft can be edited. Make a new version."
        )
    new = {**body.blueprint, "niche": row.blueprint.get("niche"), "footer": FOOTER, "schema_version": 1}
    schema = [x for x in bp.problems(new) if x.startswith("Schema /")]
    if schema:
        raise ProblemError(422, "BLUEPRINT_INVALID", "Blueprint not valid", "; ".join(schema[:5]))
    row.blueprint = new
    row.updated_at = datetime.now(UTC)
    _audit(request, db, p, "blueprint.edited", "channel_strategy", row.id, version=row.version)
    db.commit()
    return _strategy_out(row)


@router.post("/strategies/{strategy_id}/commands/{cmd}", response_model=StrategyOut, responses=STRATEGY_WRITE)
def strategy_command(
    strategy_id: uuid.UUID,
    cmd: Literal["propose", "approve", "reject", "new-version"],
    request: Request,
    db: Db,
    p: StrategyManage,
    body: ApproveIn | None = None,
) -> StrategyOut:
    row = _strategy(db, strategy_id, lock=True)
    allowed = {
        "propose": ("DRAFT",),
        "approve": ("PROPOSED",),
        "reject": ("DRAFT", "PROPOSED"),
        "new-version": ("DRAFT", "PROPOSED", "APPROVED", "REJECTED"),
    }[cmd]
    if row.status not in allowed:
        raise ProblemError(
            409, "INVALID_TRANSITION", "Not possible now", f"A {row.status.lower()} blueprint cannot '{cmd}'."
        )
    if cmd in ("propose", "approve"):
        found = bp.problems(row.blueprint)
        if found:
            raise ProblemError(409, "BLUEPRINT_HAS_PROBLEMS", "Fix the problems first", "; ".join(found[:5]))
    now = datetime.now(UTC)
    if cmd == "propose":
        row.status = "PROPOSED"
    elif cmd == "reject":
        row.status = "REJECTED"
    elif cmd == "new-version":
        top = db.scalar(
            select(func.max(ChannelStrategy.version)).where(
                (ChannelStrategy.niche_candidate_id == row.niche_candidate_id)
                if row.channel_id is None
                else (ChannelStrategy.channel_id == row.channel_id)
            )
        )
        copy = ChannelStrategy(
            id=uuid7(),
            channel_id=row.channel_id,
            niche_candidate_id=row.niche_candidate_id,
            version=int(top or row.version) + 1,
            status="DRAFT",
            blueprint=dict(row.blueprint),
        )
        db.add(copy)
        db.flush()
        _audit(request, db, p, "blueprint.new_version", "channel_strategy", copy.id, version=copy.version)
        db.commit()
        return _strategy_out(copy)
    else:
        if body is None:
            raise ProblemError(422, "CHANNEL_NAME_REQUIRED", "Name needed", "Choose the channel name.")
        if not p.has("channel.manage"):
            raise ProblemError(
                403, "FORBIDDEN", "Not allowed", "Approving creates a channel (channel.manage)."
            )
        niche = row.blueprint.get("niche", {})
        channel = Channel(
            id=uuid7(),
            state="APPROVED",
            name=body.channel_name.strip(),
            content_language=str(niche.get("language", "en")),
            is_test_channel=body.is_test_channel,
            is_monetised=False,  # a brand-new channel is not in the YouTube Partner Programme
        )
        db.add(channel)
        db.flush()
        db.add(ChannelPublishingRules(channel_id=channel.id))
        row.channel_id = channel.id
        row.status = "APPROVED"
        row.approved_by = p.user.id
        row.approved_at = now
        if row.niche_candidate_id is not None:
            cand = db.get(NicheCandidate, row.niche_candidate_id, with_for_update=True)
            if cand is not None:
                cand.status = "CONVERTED"
            for other in db.scalars(
                select(ChannelStrategy).where(
                    ChannelStrategy.niche_candidate_id == row.niche_candidate_id,
                    ChannelStrategy.id != row.id,
                    ChannelStrategy.status.in_(("DRAFT", "PROPOSED")),
                )
            ):
                other.status = "SUPERSEDED"
        _audit(
            request,
            db,
            p,
            "channel.created",
            "channel",
            channel.id,
            name=channel.name,
            from_blueprint=str(row.id),
        )
    row.updated_at = now
    _audit(request, db, p, f"blueprint.{cmd}", "channel_strategy", row.id, version=row.version)
    db.commit()
    return _strategy_out(row)
