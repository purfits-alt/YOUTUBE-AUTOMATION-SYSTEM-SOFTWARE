"""Discovery pipelines (CHANNEL_DISCOVERY_SPEC §3–§6). Run in workers, never in the API.

- :func:`run_discovery` — collect ≤ 40 documents (Wikipedia pageviews for seed topics + items of
  the owner's enabled feeds), compute pageview metrics in code, ask A02, keep only candidates that
  pass the evidence rule, the ``avoid`` list and the forbidden-phrase scan, score them in code.
- :func:`run_trend_scan` — A03 for one channel: signals (pageview z-score, feed frequency) are
  computed here; A03 only clusters and summarises; strengths and expiry are enforced here.
- :func:`run_keywords` — A05 for one channel; no invented search volumes.
- :func:`generate_blueprint` — A07 + A06 for a shortlisted candidate → blueprint DRAFT.

"Let TubeForge suggest" (no interests) uses a fixed list of broad, advertiser-friendly topics that
can be produced on H-LITE. It needs English; other languages need the owner's interests, given as
Wikipedia article titles in that language.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    ChannelStrategy,
    Keyword,
    NicheCandidate,
    NicheReport,
    ResearchSource,
    SourceDocument,
    TrendItem,
)
from tubeforge.gateway.core import Gateway
from tubeforge.research import blueprint as bp
from tubeforge.research import rss, wikipedia
from tubeforge.research.fetcher import FetchError, ResearchFetcher
from tubeforge.research.forbidden import scan
from tubeforge.research.net import FetchBlockedError
from tubeforge.research.niches import profile_weights
from tubeforge.research.sanitize import FeedError
from tubeforge.research.scoring import (
    DocRef,
    apply_weights,
    score,
    validate_criteria,
)
from tubeforge.research.signals import series_metrics, zscore_7d
from tubeforge.research.sources import SourceUnavailableError
from tubeforge_agents.base import RunOutcome, run_agent
from tubeforge_agents.discovery_agents import A02, A03, A05, A06, A07, DocIn

MAX_DOCS = 40
MAX_SEEDS = 24
HISTORY_DAYS = 365
SUGGEST_SEEDS_EN = [
    "Personal_finance", "Budget", "Cooking", "Baking", "Home_improvement", "Gardening",
    "Physical_fitness", "Computer_programming", "Spreadsheet", "Photography", "Travel", "History",
    "Astronomy", "Language_acquisition", "Study_skills", "Productivity", "Chess", "Board_game",
    "Woodworking", "Electric_vehicle", "Interior_design", "Minimalism", "Artificial_intelligence",
    "Personal_knowledge_management",
]  # fmt: skip
EXPIRY_MAX = timedelta(days=60)
EXPIRY_MIN = timedelta(days=3)
VOLUME_CLAIM = re.compile(r"\d[\d,.]*\s*[kKmM]?\s*(?:searches|search volume|monthly|per month|/mo)\b", re.I)


class PipelineError(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Collected:
    documents: list[DocIn] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    refs: dict[str, DocRef] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


def _doc(collected: Collected, doc: SourceDocument, text: str) -> None:
    key = str(doc.id)
    if key in collected.refs:
        return
    collected.refs[key] = DocRef(doc.url, doc.title)
    collected.documents.append(DocIn(id=key, url=doc.url, title=doc.title, text=text[:4000]))


def _monthly(points: list[tuple[date, int]]) -> str:
    months: dict[str, int] = {}
    for d, v in points:
        months[d.strftime("%Y-%m")] = months.get(d.strftime("%Y-%m"), 0) + v
    return ", ".join(f"{m}: {v}" for m, v in sorted(months.items())[-13:])


def _avoid_hit(text: str, avoid: list[str]) -> bool:
    low = text.lower()
    return any(a.strip().lower() in low for a in avoid if a.strip())


def collect(db: Session, fetcher: ResearchFetcher, params: dict[str, Any], *, today: date) -> Collected:
    out = Collected()
    avoid = [str(a) for a in params.get("avoid", [])]
    interests = [str(i) for i in params.get("interests", [])]
    end = today - timedelta(days=1)
    start = end - timedelta(days=HISTORY_DAYS - 1)
    wiki = wikipedia.WikipediaPageviews(db, fetcher)
    seeds: list[tuple[str, str]] = []
    for lang in params.get("languages", ["en"]):
        topics = interests or (SUGGEST_SEEDS_EN if lang == "en" else [])
        if not topics:
            out.skipped.append(f"No suggestion list for '{lang}': add interests as {lang} Wikipedia titles.")
        seeds += [(f"{lang}.wikipedia", t) for t in topics if not _avoid_hit(t.replace("_", " "), avoid)]
    for project, article in seeds[:MAX_SEEDS]:
        try:
            series = wiki.per_article(project, article, start, end)
        except (FetchError, ValueError) as exc:
            out.skipped.append(f"{project}/{article}: {exc}")
            continue
        if not series.points:
            out.skipped.append(f"{project}/{article}: no pageviews")
            continue
        m = series_metrics(series.points)
        doc = db.get_one(SourceDocument, uuid.UUID(series.document_id))
        _doc(
            out,
            doc,
            f"{doc.title}\nMonthly pageviews (people): {_monthly(series.points)}\n"
            f"Average per day: {m.avg_daily}; last 90 days vs previous 90: "
            f"{'n/a' if m.growth_pct is None else f'{m.growth_pct:+.1f}%'}",
        )
        out.metrics.append(
            {
                "document_id": series.document_id,
                "project": project,
                "article": article,
                "days": m.days,
                "avg_daily": m.avg_daily,
                "growth_pct_90d": m.growth_pct,
                "demand_hint": m.demand_hint,
                "rising_hint": m.rising_hint,
                "evergreen_hint": m.evergreen_hint,
            }
        )
    feeds = db.scalars(
        select(ResearchSource).where(
            ResearchSource.kind == "RSS", ResearchSource.enabled, ResearchSource.approval_status == "APPROVED"
        )
    ).all()
    for source in feeds:
        if len(out.documents) >= MAX_DOCS:
            break
        try:
            result = rss.read_feed(db, fetcher, source)
        except (FetchError, FetchBlockedError, FeedError, SourceUnavailableError) as exc:
            out.skipped.append(f"{source.code}: {exc}")
            continue
        for item, doc_id in result.items:
            if len(out.documents) >= MAX_DOCS:
                break
            if not _avoid_hit(item.title, avoid):
                _doc(out, db.get_one(SourceDocument, uuid.UUID(doc_id)), f"{item.title}\n{item.summary}")
    return out


def _outcome_error(outcome: RunOutcome) -> PipelineError:
    run = outcome.run
    status = {"WAITING_QUOTA": "WAITING_QUOTA", "ABORTED": "STOPPED"}.get(run.status, "FAILED")
    return PipelineError(status, run.error_detail or run.status)


def run_discovery(
    db: Session,
    gateway: Gateway,
    fetcher: ResearchFetcher,
    report_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> NicheReport:
    now = now or datetime.now(UTC)
    report = db.get_one(NicheReport, report_id, with_for_update=True)
    if report.status not in ("QUEUED", "WAITING_QUOTA", "FAILED", "STOPPED"):
        return report  # already running or done: a duplicate job does nothing
    report.status = "RUNNING"
    db.commit()
    params = dict(report.params)
    result: dict[str, Any] = {}
    try:
        try:
            got = collect(db, fetcher, params, today=now.date())
        except SourceUnavailableError as exc:
            raise PipelineError("STOPPED" if exc.code == "STOPPED" else "FAILED", exc.message) from exc
        db.commit()
        result["documents"] = len(got.documents)
        result["skipped"] = got.skipped[:30]
        if not got.documents:
            raise PipelineError("FAILED", "No research documents could be collected.")
        data = {
            "languages": params.get("languages", ["en"]),
            "interests": params.get("interests", []),
            "avoid": params.get("avoid", []),
            "documents": [d.model_dump() for d in got.documents],
            "metrics": got.metrics,
        }
        outcome = run_agent(db, gateway, A02, data, idempotent=False, now=now)
        report.agent_run_id = outcome.run.id
        if outcome.data is None:
            raise _outcome_error(outcome)
        weights = profile_weights(db, params.get("weight_profile_id"))
        avoid = [str(a) for a in params.get("avoid", [])]
        dropped: list[str] = []
        kept = 0
        for cand in outcome.data.get("candidates", []):
            name = str(cand.get("name", ""))[:80]
            if _avoid_hit(f"{name} {cand.get('summary', '')}", avoid):
                dropped.append(f"{name}: matches the avoid list")
                continue
            hits = scan(cand)
            if hits:
                dropped.append(f"{name}: forbidden phrase '{hits[0].phrase}'")
                continue
            if cand.get("language") not in data["languages"]:
                dropped.append(f"{name}: language {cand.get('language')} was not requested")
                continue
            criteria = validate_criteria(cand.get("criteria", []), got.refs)
            if not criteria:
                dropped.append(f"{name}: no usable criteria")
                continue
            s = score(criteria, weights)
            db.add(
                NicheCandidate(
                    id=uuid7(),
                    report_id=report.id,
                    name=name,
                    summary=str(cand.get("summary", ""))[:600],
                    language=str(cand["language"]),
                    criteria=[
                        *apply_weights(criteria, weights),
                        {"code": "_ORIGINALITY_ANGLES", "angles": cand.get("originality_angles", [])[:5]},
                    ],
                    opportunity_score=s.value,
                    inauthentic_risk=str(cand.get("inauthentic_risk", "HIGH")),
                    production_difficulty=str(cand.get("production_difficulty", "HIGH")),
                )
            )
            kept += 1
        result.update({"candidates": kept, "dropped": dropped})
        report.status = "DONE" if kept else "FAILED"
        if not kept:
            result["error"] = "Every proposed candidate was rejected by the checks."
    except PipelineError as exc:
        report.status = exc.status
        result["error"] = exc.message[:500]
    report.params = {**params, "result": result}
    report.updated_at = now
    db.commit()
    return report


# ---------------------------------------------------------------------------------------- A03
def channel_pillars(db: Session, channel_id: uuid.UUID) -> list[str]:
    row = db.scalar(
        select(ChannelStrategy)
        .where(ChannelStrategy.channel_id == channel_id, ChannelStrategy.status == "APPROVED")
        .order_by(ChannelStrategy.version.desc())
        .limit(1)
    )
    return [str(p["name"]) for p in (row.blueprint.get("pillars", []) if row else [])][:7]


def run_trend_scan(
    db: Session,
    gateway: Gateway,
    fetcher: ResearchFetcher,
    channel_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> list[TrendItem]:
    now = now or datetime.now(UTC)
    channel = db.get_one(Channel, channel_id)
    pillars = channel_pillars(db, channel_id)
    if not pillars:
        return []
    lang = channel.content_language or "en"
    end = now.date() - timedelta(days=1)
    signals: list[dict[str, Any]] = []
    docs = Collected()
    wiki = wikipedia.WikipediaPageviews(db, fetcher)
    for pillar in pillars:
        try:
            series = wiki.per_article(f"{lang}.wikipedia", pillar, end - timedelta(days=34), end)
        except (FetchError, ValueError):
            continue
        z = zscore_7d(series.points)
        doc = db.get_one(SourceDocument, uuid.UUID(series.document_id))
        _doc(docs, doc, f"{doc.title}\nDaily pageviews, last 35 days: {[v for _d, v in series.points]}")
        signals.append(
            {
                "term": pillar,
                "pillar": pillar,
                "signal_strength": z,
                "kind": "pageviews",
                "document_ids": [str(doc.id)],
            }
        )
    feeds = db.scalars(
        select(ResearchSource).where(
            ResearchSource.kind == "RSS", ResearchSource.enabled, ResearchSource.approval_status == "APPROVED"
        )
    ).all()
    items: list[tuple[str, str, str]] = []
    for source in feeds:
        try:
            items += [(i.title, i.summary, d) for i, d in rss.read_feed(db, fetcher, source).items]
        except (FetchError, FetchBlockedError, FeedError, SourceUnavailableError):
            continue
    for pillar in pillars:
        words = [w for w in re.findall(r"\w{4,}", pillar.lower())]
        hits = [d for t, s, d in items if words and any(w in f"{t} {s}".lower() for w in words)]
        if hits:
            strength = round(min(5.0, len(hits) / 2), 2)
            signals.append(
                {
                    "term": pillar,
                    "pillar": pillar,
                    "signal_strength": strength,
                    "kind": "feeds",
                    "document_ids": hits[:10],
                }
            )
            for d in hits[:5]:
                sd = db.get_one(SourceDocument, uuid.UUID(d))
                _doc(docs, sd, sd.content_text[:1500])
    db.commit()
    strong = [s for s in signals if s["signal_strength"] >= 1.0]
    if not strong:
        return []
    outcome = run_agent(
        db,
        gateway,
        A03,
        {
            "language": lang,
            "pillars": pillars,
            "signals": strong,
            "documents": [d.model_dump() for d in docs.documents],
        },
        channel_id=channel_id,
        idempotent=False,
        now=now,
    )
    if outcome.data is None:
        raise _outcome_error(outcome)
    by_doc: dict[str, float] = {}
    for s in strong:
        for d in s["document_ids"]:
            by_doc[d] = max(by_doc.get(d, 0.0), float(s["signal_strength"]))
    created: list[TrendItem] = []
    for item in outcome.data.get("items", []):
        cited = [d for d in item.get("source_document_ids", []) if d in by_doc and d in docs.refs]
        if not cited or scan(item):
            continue
        try:
            expires = datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
        except ValueError:
            expires = now + timedelta(days=7)
        expires = min(max(expires, now + EXPIRY_MIN), now + EXPIRY_MAX)
        row = TrendItem(
            id=uuid7(),
            channel_id=channel_id,
            topic=str(item["topic"])[:80],
            summary=str(item["summary"])[:280],
            source_document_ids=[uuid.UUID(d) for d in cited],
            signal_strength=Decimal(str(round(max(by_doc[d] for d in cited), 2))),
            confidence=str(item.get("confidence", "LOW")),
            detected_at=now,
            expires_at=expires,
        )
        db.add(row)
        created.append(row)
    db.commit()
    return created


# ---------------------------------------------------------------------------------------- A05
def run_keywords(
    db: Session, gateway: Gateway, channel_id: uuid.UUID, seeds: list[str], *, now: datetime | None = None
) -> list[Keyword]:
    channel = db.get_one(Channel, channel_id)
    lang = channel.content_language or "en"
    docs = Collected()
    for seed in seeds[:10]:
        for sd in db.scalars(
            select(SourceDocument)
            .where(SourceDocument.content_text.ilike(f"%{seed.replace('%', '').replace('_', ' ')}%"))
            .order_by(SourceDocument.fetched_at.desc())
            .limit(2)
        ):
            if len(docs.documents) < 10:
                _doc(docs, sd, sd.content_text[:1500])
    outcome = run_agent(
        db,
        gateway,
        A05,
        {"language": lang, "seeds": seeds[:10], "documents": [d.model_dump() for d in docs.documents]},
        channel_id=channel_id,
        idempotent=False,
        now=now,
    )
    if outcome.data is None:
        raise _outcome_error(outcome)
    saved: list[Keyword] = []
    for item in outcome.data.get("items", []):
        evidence = [
            {"source_document_id": e["source_document_id"], "url": docs.refs[e["source_document_id"]].url,
             "quote": str(e.get("quote", ""))[:300]}
            for e in item.get("evidence", []) if e.get("source_document_id") in docs.refs
        ]  # fmt: skip
        claims_volume = VOLUME_CLAIM.search(f"{item['phrase']} {item.get('rationale', '')}")
        if (claims_volume and not evidence) or scan(item):
            continue
        phrase = str(item["phrase"]).strip()[:80]
        existing = db.scalar(
            select(Keyword).where(Keyword.channel_id == channel_id, Keyword.phrase == phrase)
        )
        notes = (
            f"{item['intent']} · {item.get('confidence', 'LOW')} confidence · {item.get('rationale', '')}"[
                :500
            ]
        )
        if existing is None:
            existing = Keyword(id=uuid7(), channel_id=channel_id, phrase=phrase, language=lang)
            db.add(existing)
        existing.evidence = evidence
        existing.notes = notes
        saved.append(existing)
    db.commit()
    return saved


# ----------------------------------------------------------------------------------- A06 + A07
@dataclass(frozen=True)
class BlueprintResult:
    strategy: ChannelStrategy
    problems: list[str]


def _dedupe_ideas(strategy: dict[str, Any]) -> dict[str, Any]:
    ideas = list(strategy.get("ideas", []))
    drop = {j for _i, j, _s in bp.near_duplicates([str(x.get("title", "")) for x in ideas])}
    keep = [i for i in range(len(ideas)) if i not in drop][: bp.IDEAS]
    remap = {old: new for new, old in enumerate(keep)}
    calendar = [
        {**e, "idea_ref": remap[int(e["idea_ref"])]}
        for e in strategy.get("calendar_30d", [])
        if int(e.get("idea_ref", -1)) in remap
    ]
    return {**strategy, "ideas": [ideas[i] for i in keep], "calendar_30d": calendar}


def generate_blueprint(
    db: Session,
    gateway: Gateway,
    candidate_id: uuid.UUID,
    *,
    owner_notes: str = "",
    now: datetime | None = None,
) -> BlueprintResult:
    cand = db.get_one(NicheCandidate, candidate_id)
    if cand.status != "SHORTLISTED":
        raise PipelineError("FAILED", "Shortlist the niche before generating a blueprint.")
    angles: list[str] = next(
        (c.get("angles", []) for c in cand.criteria if c.get("code") == "_ORIGINALITY_ANGLES"), []
    )
    niche = {
        "name": cand.name,
        "summary": cand.summary,
        "language": cand.language,
        "originality_angles": angles,
    }
    branding = run_agent(db, gateway, A07, {"niche": niche}, idempotent=False, now=now)
    if branding.data is None:
        raise _outcome_error(branding)
    strategy = run_agent(
        db, gateway, A06, {"niche": niche, "owner_notes": owner_notes}, idempotent=False, now=now
    )
    if strategy.data is None:
        raise _outcome_error(strategy)
    blueprint = bp.compose(
        {"candidate_id": str(cand.id), "name": cand.name, "language": cand.language},
        _dedupe_ideas(strategy.data),
        branding.data,
    )
    found = bp.problems(blueprint)
    hard = [p for p in found if p.startswith("Schema /") or "Forbidden phrase" in p]
    if hard:
        raise PipelineError("FAILED", "The blueprint did not pass the checks: " + "; ".join(hard[:5]))
    version = (
        db.scalar(
            select(func.coalesce(func.max(ChannelStrategy.version), 0)).where(
                ChannelStrategy.niche_candidate_id == cand.id
            )
        )
        or 0
    ) + 1
    row = ChannelStrategy(
        id=uuid7(),
        channel_id=None,
        niche_candidate_id=cand.id,
        version=version,
        status="DRAFT",
        blueprint=blueprint,
        agent_run_id=strategy.run.id,
    )
    db.add(row)
    db.commit()
    return BlueprintResult(row, found)
