"""Providers, usage and budgets (BACKEND_SPECIFICATION §4.17, COST_CONTROL_SPEC).

Provider codes contain ``:`` and ``/`` (``groq:openai/gpt-oss-20b``), so routes take them with the
``provider`` path converter: one or more segments, none of which is a sub-resource name. That keeps
``PATCH /providers/x/verify`` from being read as provider ``x/verify`` (it answers 405, not 403/404).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.convertors import CONVERTOR_TYPES, Convertor, register_url_convertor

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require, require_recent_reauth
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.audit import record, security_event
from tubeforge.db.ids import uuid7
from tubeforge.db.models import CostBudget, ProviderRegistry, UsageLimit
from tubeforge.gateway import limits, paid, registry


class ProviderCodeConvertor(Convertor[str]):
    """Path segments of a provider code; never a sub-resource name such as ``verify``."""

    regex = (
        r"[A-Za-z0-9][A-Za-z0-9._:-]*"
        r"(?:/(?!(?:verify|credentials|paid-activation)(?:/|$))[A-Za-z0-9][A-Za-z0-9._:-]*)*"
    )

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


if "provider" not in CONVERTOR_TYPES:
    register_url_convertor("provider", ProviderCodeConvertor())

router = APIRouter(tags=["providers"])
View = Annotated[Principal, Depends(require("providers.view"))]
Manage = Annotated[Principal, Depends(require("providers.manage"))]
Paid = Annotated[Principal, Depends(require("providers.paid"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc(
        "USE_PAID_ACTIVATION / STEP1_REQUIRED / TOO_SOON / STEP1_EXPIRED / PHRASE_MISMATCH / CAP_*"
    ),
    422: problem_doc("IDEMPOTENCY_MISMATCH"),
}
REVERIFY_AFTER = timedelta(days=90)
Metric = Literal["REQUESTS", "TOKENS", "CHARS", "SECONDS", "IMAGES"]
Period = Literal["MINUTE", "DAY", "MONTH"]


class LimitIO(BaseModel):
    metric: Metric
    period: Period
    limit_value: int = Field(ge=0, le=10_000_000_000)


class ProviderOut(BaseModel):
    code: str
    family: str
    capability: str
    tier: Literal["L", "F", "P"]
    enabled: bool
    paid_activation_step: int
    licence: str
    licence_url: str | None
    commercial_use: str
    data_use_training: bool | None
    published_limits: dict[str, Any]
    limits: list[LimitIO]
    has_key: bool
    needs_key: bool
    verified_at: date
    verified_url: str
    reverify_due: bool
    notes: str | None


class ProviderPatch(BaseModel):
    enabled: bool | None = None
    limits: list[LimitIO] | None = Field(default=None, max_length=12)


class ProviderPatchOut(BaseModel):
    provider: ProviderOut
    warnings: list[str]


class KeyIn(BaseModel):
    secret: str = Field(min_length=8, max_length=400, pattern=r"^[\x21-\x7e]+$", description="Write-only.")


class VerifyIn(BaseModel):
    verified_url: str = Field(pattern=r"^https://\S{3,490}$")
    notes: str | None = Field(default=None, max_length=1000)


class Step1In(BaseModel):
    acknowledge_cost: Literal[True]


class Step1Out(BaseModel):
    code: str
    estimate: dict[str, Any]
    confirm_phrase: str
    earliest_step2_at: datetime


class Step2In(BaseModel):
    confirm_phrase: str = Field(max_length=200)
    monthly_cap_minor: int = Field(ge=1, le=100_000_000)


class UsageLine(BaseModel):
    provider_code: str
    metric: str
    period: str
    period_key: str
    used: int
    limit: int | None
    pct: int | None
    resets_at: datetime


class BudgetOut(BaseModel):
    scope: Literal["STOCK", "PAID_PROVIDER"]
    provider_code: str | None
    month: str
    cap_minor: int
    spent_minor: int
    currency: str


class BudgetIn(BaseModel):
    scope: Literal["STOCK", "PAID_PROVIDER"]
    provider_code: str | None = Field(default=None, max_length=120)
    cap_minor: int = Field(ge=0, le=100_000_000)


class CostSummary(BaseModel):
    month: str
    spent_minor: int
    paid_enabled: list[str]


def _provider(db: Session, code: str, *, lock: bool = False) -> ProviderRegistry:
    row = db.get(ProviderRegistry, code, with_for_update=lock)
    if row is None:
        raise not_found("No such provider.")
    return row


def _out(db: Session, row: ProviderRegistry) -> ProviderOut:
    lims = db.scalars(
        select(UsageLimit)
        .where(UsageLimit.provider_code == row.code, UsageLimit.scope == "GLOBAL")
        .order_by(UsageLimit.metric, UsageLimit.period)
    ).all()
    fam = registry.family(row.code)
    return ProviderOut(
        code=row.code,
        family=fam,
        capability=row.capability,
        tier=row.tier,
        enabled=row.enabled,
        paid_activation_step=row.paid_activation_step,
        licence=row.licence,
        licence_url=row.licence_url,
        commercial_use=row.commercial_use,
        data_use_training=row.data_use_training,
        published_limits={k: v for k, v in (row.limits or {}).items()},
        limits=[LimitIO(metric=x.metric, period=x.period, limit_value=x.limit_value) for x in lims],
        has_key=registry.has_key(db, row.code),
        needs_key=fam not in registry.KEYLESS_FAMILIES,
        verified_at=row.verified_at,
        verified_url=row.verified_url,
        reverify_due=row.verified_at + REVERIFY_AFTER <= datetime.now(UTC).date(),
        notes=row.notes,
    )


def _audit(request: Request, db: Session, p: Principal, action: str, code: str, **details: Any) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="provider",
        entity_id=code,
        details=details or None,
        request_id=request_id(request),
        ip=client_ip(request),
    )


def _paid_problem(exc: paid.PaidActivationError) -> ProblemError:
    return ProblemError(409, exc.code, "Paid activation", exc.message)


# ------------------------------------------------------------------------------------- providers
@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Db, _: View) -> list[ProviderOut]:
    rows = db.scalars(
        select(ProviderRegistry).order_by(ProviderRegistry.tier.desc(), ProviderRegistry.code)
    ).all()
    return [_out(db, r) for r in rows]


@router.patch("/providers/{code:provider}", response_model=ProviderPatchOut, responses=WRITE)
def patch_provider(code: str, body: ProviderPatch, request: Request, db: Db, p: Manage) -> ProviderPatchOut:
    row = _provider(db, code, lock=True)
    warnings: list[str] = []
    if body.enabled is not None:
        if row.tier == "P" and body.enabled:
            raise ProblemError(
                409,
                "USE_PAID_ACTIVATION",
                "Paid provider",
                "Paid providers are enabled with the two-step activation.",
            )
        row.enabled = body.enabled
        if body.enabled and row.data_use_training is not False and row.tier != "L":
            warnings.append(
                "This provider may use your content to improve its products. Local-only channels skip it."
            )
    if body.limits is not None:
        for lim in body.limits:
            db.execute(
                delete(UsageLimit).where(
                    UsageLimit.provider_code == code,
                    UsageLimit.scope == "GLOBAL",
                    UsageLimit.metric == lim.metric,
                    UsageLimit.period == lim.period,
                )
            )
            db.add(
                UsageLimit(
                    id=uuid7(),
                    provider_code=code,
                    scope="GLOBAL",
                    scope_ref=None,
                    metric=lim.metric,
                    period=lim.period,
                    limit_value=lim.limit_value,
                )
            )
        if isinstance(row.limits, dict) and row.limits.get("placeholder"):
            row.limits = {k: v for k, v in row.limits.items() if k != "placeholder"}
    _audit(
        request,
        db,
        p,
        "provider.updated",
        code,
        enabled=row.enabled,
        limits=[x.model_dump() for x in body.limits or []],
    )
    db.commit()
    return ProviderPatchOut(provider=_out(db, row), warnings=warnings)


@router.put("/providers/{code:provider}/credentials", status_code=204, responses=WRITE)
def put_key(code: str, body: KeyIn, request: Request, db: Db, p: Manage) -> Response:
    row = _provider(db, code)
    fam = registry.family(row.code)
    if fam in registry.KEYLESS_FAMILIES:
        raise ProblemError(409, "NO_KEY_NEEDED", "No key needed", "This provider runs on your PC.")
    n = registry.set_family_key(db, request.app.state.secret_box, fam, body.secret)
    _audit(request, db, p, "provider.key_set", fam, rows=n)
    security_event(db, "PROVIDER_KEY_SET", "INFO", user_id=p.user.id, details={"family": fam})
    db.commit()
    return Response(status_code=204)


@router.delete("/providers/{code:provider}/credentials", status_code=204)
def delete_key(code: str, request: Request, db: Db, p: Manage) -> Response:
    fam = registry.family(_provider(db, code).code)
    registry.delete_family_key(db, fam)
    _audit(request, db, p, "provider.key_deleted", fam)
    db.commit()
    return Response(status_code=204)


@router.post("/providers/{code:provider}/verify", response_model=ProviderOut)
def verify(code: str, body: VerifyIn, request: Request, db: Db, p: Manage) -> ProviderOut:
    row = _provider(db, code, lock=True)
    row.verified_at = datetime.now(UTC).date()
    row.verified_url = body.verified_url
    if body.notes is not None:
        row.notes = body.notes
    _audit(request, db, p, "provider.verified", code, url=body.verified_url)
    db.commit()
    return _out(db, row)


@router.post("/providers/{code:provider}/paid-activation/step1", response_model=Step1Out, responses=WRITE)
def paid_step1(code: str, body: Step1In, request: Request, db: Db, p: Paid) -> Step1Out:
    require_recent_reauth(p)
    try:
        row = paid.step1(db, code, actor=p.actor)
    except paid.PaidActivationError as exc:
        raise _paid_problem(exc) from exc
    db.commit()
    return Step1Out(
        code=code,
        estimate=paid.cost_estimate(row),
        confirm_phrase=paid.confirm_phrase(code),
        earliest_step2_at=datetime.now(UTC) + paid.STEP_GAP,
    )


@router.post("/providers/{code:provider}/paid-activation/step2", response_model=ProviderOut, responses=WRITE)
def paid_step2(code: str, body: Step2In, request: Request, db: Db, p: Paid) -> Any:
    require_recent_reauth(p)
    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    try:
        row = paid.step2(
            db, code, phrase=body.confirm_phrase, monthly_cap_minor=body.monthly_cap_minor, actor=p.actor
        )
    except paid.PaidActivationError as exc:
        db.commit()  # keep a step 1 reset by an expired window
        raise _paid_problem(exc) from exc
    out = _out(db, row)
    idem.store(200, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post(
    "/providers/{code:provider}/paid-activation/disable", response_model=ProviderOut, responses=WRITE
)
def paid_disable(code: str, request: Request, db: Db, p: Paid) -> ProviderOut:
    """One click, immediate (no re-auth: switching money off must never be hard)."""
    try:
        row = paid.disable(db, code, actor=p.actor)
    except paid.PaidActivationError as exc:
        raise _paid_problem(exc) from exc
    db.commit()
    return _out(db, row)


# ----------------------------------------------------------------------------------------- usage
@router.get("/usage", response_model=list[UsageLine])
def usage(db: Db, _: View, period: Annotated[Literal["day", "month"], Query()] = "day") -> list[UsageLine]:
    now = datetime.now(UTC)
    per = period.upper()
    key = limits.period_key(per, limits.PT, now)
    lims = {
        (x.provider_code, x.metric): x.limit_value
        for x in db.scalars(select(UsageLimit).where(UsageLimit.scope == "GLOBAL", UsageLimit.period == per))
    }
    out = []
    for row in db.scalars(select(ProviderRegistry).order_by(ProviderRegistry.code)):
        for metric in ("REQUESTS", "TOKENS"):
            used = limits.used(db, row.code, metric, key)
            cap = lims.get((row.code, metric))
            if used == 0 and cap is None:
                continue
            out.append(
                UsageLine(
                    provider_code=row.code,
                    metric=metric,
                    period=per,
                    period_key=key,
                    used=used,
                    limit=cap,
                    pct=None if not cap else min(999, round(used * 100 / cap)),
                    resets_at=limits.next_reset(per, limits.PT, now),
                )
            )
    return out


@router.get("/costs/summary", response_model=CostSummary)
def cost_summary(db: Db, _: View) -> CostSummary:
    month = paid.month_key(datetime.now(UTC))
    spent = sum(b.spent_minor for b in db.scalars(select(CostBudget).where(CostBudget.month == month)))
    enabled = [
        r.code
        for r in db.scalars(
            select(ProviderRegistry).where(ProviderRegistry.tier == "P", ProviderRegistry.enabled.is_(True))
        )
    ]
    return CostSummary(month=month, spent_minor=spent, paid_enabled=enabled)


@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(db: Db, _: View) -> list[BudgetOut]:
    month = paid.month_key(datetime.now(UTC))
    rows = db.scalars(select(CostBudget).where(CostBudget.month == month).order_by(CostBudget.scope)).all()
    return [BudgetOut.model_validate(r, from_attributes=True) for r in rows]


@router.put("/budgets", response_model=BudgetOut, responses=WRITE)
def put_budget(body: BudgetIn, request: Request, db: Db, p: Paid) -> BudgetOut:
    if body.scope == "PAID_PROVIDER" and not body.provider_code:
        raise ProblemError(
            400, "VALIDATION_ERROR", "Invalid request", "A paid-provider budget names its provider."
        )
    current = paid.budget(db, scope=body.scope, provider_code=body.provider_code)
    if body.cap_minor > (current.cap_minor if current else 0):
        require_recent_reauth(p)  # raising a cap is a money decision
    try:
        row = paid.set_cap(db, scope=body.scope, provider_code=body.provider_code, cap_minor=body.cap_minor)
    except paid.PaidActivationError as exc:
        raise _paid_problem(exc) from exc
    record(
        db,
        actor=p.actor,
        action="budget.set",
        entity_type="cost_budget",
        entity_id=str(row.id),
        details={"scope": body.scope, "provider": body.provider_code, "cap_minor": body.cap_minor},
        request_id=request_id(request),
        ip=client_ip(request),
    )
    db.commit()
    return BudgetOut.model_validate(row, from_attributes=True)
