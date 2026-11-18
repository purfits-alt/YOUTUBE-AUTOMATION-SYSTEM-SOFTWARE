"""Content pipelines (Phase 7): ideas → project → research brief → script. Run in workers, never in
the API. The model drafts; code checks.

- :func:`generate_ideas` — A08 for one channel. Forbidden phrases are retried once, then dropped.
  Every idea is scored against the channel's earlier ideas with the similarity service (ADR-0029);
  ``similarity_max`` / ``similar_to_id`` feed the ``idea_original`` guard. Repeats inside one batch
  are dropped. Variation mode (``variation``) keeps only ideas clearly different from the source
  (below ``variation_max``).
- :func:`start_project` — an APPROVED idea becomes a project (packaging promise copied) and moves
  IDEA → RESEARCHING; the idea moves to IN_PRODUCTION.
- :func:`run_research` — Wikipedia articles (search + extracts) → A09 brief → claims checked in code
  (cited ids must be real documents; instruction-like text is dropped) → A10 on the claims →
  ``fact_check_claims`` rows → ``research_done``.
- :func:`run_script` — A11 from the approved brief → craft validators (``tubeforge.content.craft``),
  one repair call listing every failed check → script version → A10 on the script → ``script_done``.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.audit import Actor
from tubeforge.content import craft, scripts, similarity
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    Channel,
    FactCheckClaim,
    OwnerValueAdd,
    ResearchBrief,
    Script,
    ScriptVersion,
    SourceDocument,
    TrendItem,
    VideoIdea,
    VideoProject,
)
from tubeforge.gateway.core import Gateway
from tubeforge.logging import get_logger
from tubeforge.notifications import notify_owners
from tubeforge.orchestrator import engine
from tubeforge.orchestrator.machines import MACHINES
from tubeforge.research import forbidden
from tubeforge.research.fetcher import FetchError, ResearchFetcher
from tubeforge.research.net import FetchBlockedError
from tubeforge.research.sources import SourceUnavailableError
from tubeforge.research.wiki_articles import LANGUAGES, WikipediaArticles
from tubeforge_agents.base import RunOutcome, run_agent
from tubeforge_agents.content_agents import A08, A09, A10, A11
from tubeforge_agents.discovery import (
    PipelineError,
    _outcome_error,
    _run_clean,
    channel_brief,
    channel_pillars,
)
from tubeforge_agents.discovery_agents import DocIn

log = get_logger("tubeforge.content")

ORCH = Actor("ORCH", "orchestrator")
DEFAULT_DURATION_S = {"LONG": 480, "SHORT": 45}
RENDER_PROFILE = {"LONG": {"profile": "LONG_1080"}, "SHORT": {"profile": "SHORT_1080"}}
RECENT_TITLES = 80
MAX_ARTICLES = 6
MIN_DOCUMENTS = 2
MAX_QUERIES = 8
# Text that reads like an instruction to the model (prompt injection copied from a source).
INSTRUCTION_LIKE = re.compile(
    r"(?i)(\bsystem\s*:|\bignore (?:all |the |any |previous |prior )*(?:rules|instructions)\b"
    r"|\bsubscribe to win\b|\bwin an? iphone\b|\byou are now\b|\bdisregard (?:the|all|your)\b)"
)


# ------------------------------------------------------------------------------------- ideas
@dataclass
class IdeasResult:
    ideas: list[VideoIdea] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    method: str = "trigram"


@dataclass(frozen=True)
class Variation:
    """An owner's own video to vary (US-4.6). The API checks that it belongs to the channel."""

    youtube_video_id: str
    title: str
    kind: str
    angle: str = ""
    format: str = "LONG"


def _decimal(x: float) -> Decimal:
    return Decimal(str(round(min(max(x, 0.0), 1.0), 3)))


def generate_ideas(
    db: Session,
    gateway: Gateway,
    channel_id: uuid.UUID,
    *,
    count: int = 10,
    fmt: str | None = None,
    pillar: str | None = None,
    variation: Variation | None = None,
    now: datetime | None = None,
) -> IdeasResult:
    now = now or datetime.now(UTC)
    channel = db.get_one(Channel, channel_id)
    pillars = channel_pillars(db, channel_id) or ([pillar] if pillar else ["General"])
    existing = list(
        db.scalars(
            select(VideoIdea)
            .where(VideoIdea.channel_id == channel_id, VideoIdea.deleted_at.is_(None))
            .order_by(VideoIdea.created_at.desc())
        )
    )
    trends = list(
        db.scalars(
            select(TrendItem)
            .where(
                TrendItem.channel_id == channel_id,
                TrendItem.status == "ACTIVE",
                TrendItem.expires_at > now,
            )
            .order_by(TrendItem.signal_strength.desc())
            .limit(20)
        )
    )
    data: dict[str, Any] = {
        "language": channel.content_language if channel.content_language in LANGUAGES else "en",
        "count": count,
        "pillars": pillars,
        "channel_brief": channel_brief(db, channel),
        "format": fmt,
        "pillar": pillar,
        "recent_titles": [i.title for i in existing[:RECENT_TITLES]],
        "trends": [{"id": str(t.id), "term": t.topic[:120]} for t in trends],
    }
    if variation is not None:
        data["variation_of"] = {
            "title": variation.title,
            "angle": variation.angle,
            "format": variation.format,
            "kind": variation.kind,
        }
    outcome = _run_clean(db, gateway, A08, data, now, channel_id)
    sim = similarity.get_similarity()
    limits = similarity.limits_for(sim)
    result = IdeasResult(method=sim.method)
    trend_by_id = {str(t.id): t for t in trends}
    corpus = [i.title for i in existing]
    batch: list[str] = []
    for item in outcome.data.get("items", [])[:count]:
        title = str(item.get("title", "")).strip()[:100]
        if not title:
            continue
        hits = forbidden.scan(item)
        if hits:
            result.dropped.append(f"{title}: forbidden phrase '{hits[0].phrase}'")
            continue
        repeat = similarity.nearest(title, batch, sim)
        if repeat.index is not None and repeat.score >= limits.duplicate:
            result.dropped.append(f"{title}: repeats another idea in this batch ({repeat.score:.2f})")
            continue
        near = similarity.nearest(title, corpus, sim)
        to_source: float | None = None
        if variation is not None:
            to_source = similarity.nearest(title, [variation.title], sim).score
            if to_source >= limits.variation_max:
                result.dropped.append(
                    f"{title}: too close to the source video ({to_source:.2f} ≥ {limits.variation_max:.2f})"
                )
                continue
        trend = trend_by_id.get(str(item.get("trend_item_id") or ""))
        idea_format = str(item.get("format", "LONG"))
        idea = VideoIdea(
            id=uuid7(),
            channel_id=channel_id,
            state="SUGGESTED",
            title=title,
            angle=str(item.get("angle", ""))[:500],
            target_viewer=str(item.get("target_viewer", ""))[:200] or None,
            format=idea_format if idea_format in ("LONG", "SHORT") else "LONG",
            pillar=next((p for p in pillars if p.lower() == str(item.get("pillar", "")).lower()), None),
            trend_item_id=trend.id if trend else None,
            originality_notes=str(item.get("originality_notes", ""))[:300] or None,
            similarity_max=_decimal(near.score) if near.index is not None else None,
            similar_to_id=existing[near.index].id if near.index is not None else None,
            expires_at=trend.expires_at if trend else None,
            source="REPLICATE" if variation else "AGENT",
            based_on_youtube_video_id=variation.youtube_video_id if variation else None,
            variation_kind=variation.kind if variation else None,
            similarity_to_source=_decimal(to_source) if to_source is not None else None,
            packaging_promise=dict(item.get("packaging_promise") or {}) or None,
            owner_value_add_prompt=str(item.get("owner_value_add_prompt", ""))[:200] or None,
        )
        db.add(idea)
        result.ideas.append(idea)
        batch.append(title)
    db.commit()
    log.info(
        "ideas.generated", channel_id=str(channel_id), kept=len(result.ideas), dropped=len(result.dropped)
    )
    return result


# ------------------------------------------------------------------------------------ project
def start_project(
    db: Session,
    idea_id: uuid.UUID,
    *,
    target_duration_s: int | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> VideoProject:
    """APPROVED idea → project in RESEARCHING (the orchestrator's step after the owner's approval).
    The API passes ``commit=False`` so the approval, the project and the research job share one
    transaction."""
    idea = db.get_one(VideoIdea, idea_id)
    if idea.state != "APPROVED":
        raise PipelineError("FAILED", "Approve the idea first.")
    project = VideoProject(
        id=uuid7(),
        channel_id=idea.channel_id,
        idea_id=idea.id,
        format=idea.format,
        state="IDEA",
        working_title=idea.title,
        packaging_promise=idea.packaging_promise,
        target_duration_s=target_duration_s or DEFAULT_DURATION_S[idea.format],
        render_profile=dict(RENDER_PROFILE[idea.format]),
    )
    db.add(project)
    db.flush()
    db.add(OwnerValueAdd(project_id=project.id))
    db.flush()
    engine.transition(
        db, MACHINES["video_idea"], idea.id, "start_production", actor=ORCH,
        idempotency_key=f"start-production:{idea.id}", now=now,
    )  # fmt: skip
    engine.transition(
        db, MACHINES["video_project"], project.id, "start_research", actor=ORCH,
        idempotency_key=f"start-research:{project.id}", now=now,
    )  # fmt: skip
    if commit:
        db.commit()
    return project


# ----------------------------------------------------------------------------------- research
@dataclass
class ResearchResult:
    brief: ResearchBrief
    dropped: list[str]


def _docs_for(db: Session, ids: list[str]) -> list[DocIn]:
    out: list[DocIn] = []
    for raw in ids:
        doc = db.get(SourceDocument, uuid.UUID(raw))
        if doc is not None:
            out.append(DocIn(id=str(doc.id), url=doc.url, title=doc.title, text=doc.content_text[:4000]))
    return out


# Minimum relevance of an article to the video topic (same 0–1 cosine as the idea checks, ADR-0029).
# model2vec: unrelated text scores ~0.0, related ~0.5; trigrams score lower overall.
RELEVANCE_MIN = {"model2vec": 0.30, "trigram": 0.05}
MAX_CANDIDATES = 12


def collect_articles(
    db: Session,
    fetcher: ResearchFetcher,
    language: str,
    queries: list[str],
    *,
    topic: str = "",
    pinned_queries: Sequence[str] = (),
) -> tuple[list[DocIn], list[str]]:
    """Search Wikipedia, read up to ``MAX_CANDIDATES`` articles and keep the ``MAX_ARTICLES`` most
    relevant to ``topic``. Articles found with the owner's own search words are always kept; others
    must reach ``RELEVANCE_MIN`` (owner report 2026-11-17: loose searches returned unrelated pages
    such as San Francisco history for a video about AI sampling settings)."""
    wiki = WikipediaArticles(db, fetcher)
    titles: list[str] = []
    pinned: set[str] = set()
    skipped: list[str] = []
    for q in queries:
        if not q.strip():
            continue
        try:
            for t in wiki.search(language, q, limit=4):
                if q in pinned_queries:
                    pinned.add(t)
                if t not in titles:
                    titles.append(t)
        except (FetchError, FetchBlockedError) as exc:
            skipped.append(f"search '{q[:60]}': {exc}")
    found: list[tuple[str, str]] = []
    for t in titles[:MAX_CANDIDATES]:
        try:
            art = wiki.article(language, t)
        except (FetchError, FetchBlockedError) as exc:
            skipped.append(f"{t}: {exc}")
            continue
        if art is not None:
            found.append((t, art.document_id))
    db.commit()
    docs = _docs_for(db, [doc_id for _, doc_id in found])
    if not topic.strip() or not docs:
        return docs[:MAX_ARTICLES], skipped
    sim = similarity.get_similarity()
    floor = RELEVANCE_MIN.get(sim.method, 0.0)
    scores = sim.against(topic, [f"{d.title or ''}\n{d.text[:1500]}" for d in docs])
    ranked = sorted(zip(docs, scores, [t for t, _ in found], strict=True), key=lambda x: -x[1])
    kept: list[DocIn] = []
    for doc, score, title in ranked:
        if title in pinned or score >= floor:
            kept.append(doc)
        else:
            skipped.append(f"{title}: not about this topic ({score:.2f})")
    return kept[:MAX_ARTICLES], skipped


STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "at", "by", "with", "from", "how",
    "why", "what", "when", "which", "who", "your", "my", "our", "i", "you", "we", "is", "are", "was",
    "be", "it", "this", "that", "these", "those", "vs", "versus", "into", "using", "use", "guide",
    "tips", "best", "top", "new", "free", "explained", "step", "steps", "setup", "set", "up",
})  # fmt: skip


def search_terms(title: str) -> list[str]:
    """Shorter Wikipedia searches from a long title: the names in it (CodeLlama, DeepSeek-Coder,
    VS Code) and the remaining key words, so research finds articles a whole-title search misses."""
    words = re.findall(r"[\w][\w.+#-]*", title, flags=re.UNICODE)
    names = [
        w
        for w in words
        if len(w) >= 3 and (w[0].isupper() or any(c.isdigit() for c in w)) and w.lower() not in STOPWORDS
    ]
    keys = [w for w in words if w.lower() not in STOPWORDS and len(w) >= 3]
    out = list(dict.fromkeys(names))[:4]
    if len(keys) >= 2:
        out.append(" ".join(keys[:4]))
    return out


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check_brief(brief: dict[str, Any], docs: list[DocIn]) -> tuple[dict[str, Any], list[str]]:
    """Keep claims that cite real documents and are not instructions; mark whether the quote is verbatim."""
    known = {d.id: _normal(d.text) for d in docs}
    claims: list[dict[str, Any]] = []
    dropped: list[str] = []
    for i, c in enumerate(brief.get("claims", [])):
        text = str(c.get("text", ""))
        cited = [s for s in c.get("source_document_ids", []) if s in known]
        if INSTRUCTION_LIKE.search(text) or INSTRUCTION_LIKE.search(str(c.get("quote", ""))):
            dropped.append(f"claim {c.get('id', i)}: looks like an instruction from a source")
            continue
        if not cited:
            dropped.append(f"claim {c.get('id', i)}: cites no supplied document")
            continue
        quote = _normal(str(c.get("quote", "")))
        claims.append(
            {
                **c,
                "id": str(c.get("id") or f"c{i + 1}")[:10],
                "source_document_ids": cited,
                "quote_verified": bool(quote) and any(quote in known[s] for s in cited),
            }
        )
    clean = {
        **brief,
        "claims": claims,
        "key_points": [k for k in brief.get("key_points", []) if not INSTRUCTION_LIKE.search(str(k))],
        "hook_ideas": [h for h in brief.get("hook_ideas", []) if not INSTRUCTION_LIKE.search(str(h))],
    }
    return clean, dropped


def _store_claims(
    db: Session,
    project: VideoProject,
    subject_type: str,
    subject_id: uuid.UUID,
    outcome: RunOutcome,
    docs: list[DocIn],
) -> list[FactCheckClaim]:
    known = {d.id for d in docs}
    rows: list[FactCheckClaim] = []
    for c in outcome.data.get("claims", []):
        rows.append(
            FactCheckClaim(
                id=uuid7(),
                project_id=project.id,
                channel_id=project.channel_id,
                subject_type=subject_type,
                subject_id=subject_id,
                claim_text=str(c.get("claim_text", ""))[:400],
                verdict=str(c.get("verdict", "UNSUPPORTED")),
                source_document_ids=[uuid.UUID(s) for s in c.get("source_document_ids", []) if s in known],
                explanation=str(c.get("explanation", ""))[:300],
                agent_run_id=outcome.run.id,
            )
        )
    db.add_all(rows)
    return rows


def _fact_check(
    db: Session, gateway: Gateway, project: VideoProject, text: str, docs: list[DocIn], now: datetime | None
) -> RunOutcome:
    channel = db.get_one(Channel, project.channel_id)
    language = channel.content_language if channel.content_language in LANGUAGES else "en"
    data = {"language": language, "text": text[:40000], "documents": [d.model_dump() for d in docs]}
    outcome = run_agent(
        db,
        gateway,
        A10,
        data,
        channel_id=project.channel_id,
        project_id=project.id,
        idempotent=False,
        now=now,
    )
    if outcome.data is None:
        raise _outcome_error(outcome)
    return outcome


def _verdicts_for(claims: list[dict[str, Any]], checked: list[FactCheckClaim]) -> list[dict[str, Any]]:
    """Attach the closest A10 verdict to every brief claim (claims are sent as 'id: text' lines)."""
    out: list[dict[str, Any]] = []
    for c in claims:
        verdict = "UNSUPPORTED"
        match = next((f for f in checked if f.claim_text.startswith(f"{c['id']}:")), None)
        if match is None:
            texts = [f.claim_text for f in checked]
            near = similarity.nearest(str(c.get("text", "")), texts, similarity.TrigramSimilarity())
            if near.index is not None and near.score >= 0.6:
                match = checked[near.index]
        if match is not None:
            verdict = match.verdict
        out.append({**c, "verdict": verdict})
    return out


def brief_facts(brief: ResearchBrief) -> list[dict[str, Any]]:
    """The ``claims`` fact for the ``research_brief_valid`` guard."""
    return [
        {
            "id": c.get("id"),
            "sources": len(c.get("source_document_ids", [])),
            # An owner override (``/claims/{id}/override``) turns a contradicted claim into an accepted one.
            "verdict": "overridden" if c.get("override_reason") else str(c.get("verdict", "")).lower(),
        }
        for c in brief.content.get("claims", [])
    ]


def run_research(
    db: Session,
    gateway: Gateway,
    fetcher: ResearchFetcher,
    project_id: uuid.UUID,
    *,
    extra_queries: Sequence[str] = (),
    now: datetime | None = None,
) -> ResearchResult:
    project = db.get_one(VideoProject, project_id)
    if project.state != "RESEARCHING":
        raise PipelineError("FAILED", f"The project is {project.state}, not RESEARCHING.")
    channel = db.get_one(Channel, project.channel_id)
    language = channel.content_language if channel.content_language in LANGUAGES else "en"
    idea = db.get(VideoIdea, project.idea_id) if project.idea_id else None
    promise = project.packaging_promise or {}
    queries = [
        *(q.strip() for q in extra_queries if q.strip()),
        project.working_title,
        *search_terms(project.working_title),
    ]
    if idea is not None and idea.pillar:
        queries.append(idea.pillar)
    if promise.get("title_idea"):
        queries.append(str(promise["title_idea"]))
    queries = list(dict.fromkeys(queries))[:MAX_QUERIES]
    try:
        docs, skipped = collect_articles(
            db,
            fetcher,
            language,
            queries,
            topic=" ".join(
                filter(
                    None,
                    [project.working_title, idea.angle if idea else "", promise.get("promise_statement")],
                )
            ),
            pinned_queries=[q.strip() for q in extra_queries if q.strip()],
        )
    except SourceUnavailableError as exc:
        raise PipelineError("STOPPED" if exc.code == "STOPPED" else "FAILED", exc.message) from exc
    if len(docs) < MIN_DOCUMENTS:
        raise PipelineError(
            "FAILED",
            f"Only {len(docs)} Wikipedia article(s) about “{project.working_title}” were found; at least "
            f"{MIN_DOCUMENTS} are needed. Press Research again and add the names of Wikipedia articles "
            "on this topic as extra search words, or edit the working title.",
        )
    data = {
        "language": language,
        "idea": {
            "title": project.working_title,
            "angle": idea.angle if idea else "",
            "format": project.format,
            "packaging_promise": promise or None,
        },
        "documents": [d.model_dump() for d in docs],
    }
    outcome = run_agent(
        db,
        gateway,
        A09,
        data,
        channel_id=project.channel_id,
        project_id=project.id,
        idempotent=False,
        now=now,
    )
    if outcome.data is None:
        raise _outcome_error(outcome)
    content, dropped = check_brief(outcome.data, docs)
    if not content["claims"]:
        raise PipelineError("FAILED", "The research brief has no usable claims: " + "; ".join(dropped[:5]))
    version = (
        db.scalar(
            select(func.coalesce(func.max(ResearchBrief.version), 0)).where(
                ResearchBrief.project_id == project.id
            )
        )
        or 0
    ) + 1
    brief = ResearchBrief(
        id=uuid7(),
        project_id=project.id,
        channel_id=project.channel_id,
        version=version,
        content={**content, "documents": [{"id": d.id, "url": d.url, "title": d.title} for d in docs]},
        agent_run_id=outcome.run.id,
        status="DRAFT",
    )
    db.add(brief)
    db.flush()
    text = "\n".join(f"{c['id']}: {c['text']}" for c in content["claims"])
    checked = _store_claims(
        db, project, "RESEARCH_BRIEF", brief.id, _fact_check(db, gateway, project, text, docs, now), docs
    )
    brief.content = {
        **brief.content,
        "claims": _verdicts_for(content["claims"], checked),
        "skipped": skipped[:20],
    }
    brief.status = "SUBMITTED"
    engine.transition(
        db, MACHINES["video_project"], project.id, "research_done", actor=Actor("AGENT", A09.code),
        payload={"research_done": True, "fact_check_done": True},
        idempotency_key=f"research-done:{brief.id}", now=now,
    )  # fmt: skip
    contradicted = sum(1 for c in brief.content["claims"] if c["verdict"] == "CONTRADICTED")
    notify_owners(
        db,
        event_type="research.ready",
        severity="WARNING" if contradicted else "INFO",
        title="Research brief ready for review",
        body=f"“{project.working_title}”: {len(content['claims'])} claims, {contradicted} contradicted.",
        dedup_key=f"research-ready:{brief.id}",
        channel_id=project.channel_id,
        link=f"/projects/{project.id}/script",
        entity_type="video_project",
        entity_id=project.id,
    )
    db.commit()
    return ResearchResult(brief, dropped)


# ------------------------------------------------------------------------------------- script
@dataclass
class ScriptResult:
    version: ScriptVersion
    findings: list[craft.Finding]
    repaired: bool


def recent_phrases(db: Session, channel_id: uuid.UUID, exclude: uuid.UUID, limit: int = 5) -> list[str]:
    """Openings and CTAs of the channel's latest scripts (anti-template, A11 rule 6)."""
    rows: list[dict[str, Any]] = list(
        db.execute(
            select(ScriptVersion.body)
            .join(Script, Script.id == ScriptVersion.script_id)
            .where(Script.channel_id == channel_id, Script.project_id != exclude)
            .order_by(ScriptVersion.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    phrases: list[str] = []
    for body in rows:
        for part in (str(body.get("hook", {}).get("text", "")), str(body.get("cta", ""))):
            first = re.split(r"(?<=[.!?])\s", part.strip(), maxsplit=1)[0].strip(" .!?")
            if len(first.split()) >= 4 and first not in phrases:
                phrases.append(first)
    return phrases[:40]


def _value_add(row: OwnerValueAdd | None) -> dict[str, str]:
    if row is None:
        return {}
    fields = {
        "own_opinion": row.own_opinion,
        "own_experience": row.own_experience,
        "own_data": row.own_data,
        "own_examples": row.own_examples,
    }
    return {k: v for k, v in fields.items() if v and v.strip()}


def _describe(findings: list[craft.Finding]) -> str:
    return "; ".join(f"{f.code}: {f.message}" for f in craft.errors(findings))[:3000]


def run_script(
    db: Session,
    gateway: Gateway,
    project_id: uuid.UUID,
    *,
    wpm: int = craft.DEFAULT_WPM,
    instruction: str = "",
    now: datetime | None = None,
) -> ScriptResult:
    project = db.get_one(VideoProject, project_id)
    if project.state != "SCRIPTING":
        raise PipelineError("FAILED", f"The project is {project.state}, not SCRIPTING.")
    brief = db.scalar(
        select(ResearchBrief)
        .where(ResearchBrief.project_id == project.id, ResearchBrief.status == "APPROVED")
        .order_by(ResearchBrief.version.desc())
        .limit(1)
    )
    if brief is None:
        raise PipelineError("FAILED", "Approve the research brief first.")
    channel = db.get_one(Channel, project.channel_id)
    language = channel.content_language if channel.content_language in LANGUAGES else "en"
    claims = [
        {"id": c["id"], "text": c["text"]}
        for c in brief.content.get("claims", [])
        if c.get("verdict") != "CONTRADICTED" or c.get("override_reason")
    ]
    if not claims:
        raise PipelineError("FAILED", "The approved brief has no usable claims.")
    promise = project.packaging_promise or {}
    phrases = recent_phrases(db, project.channel_id, project.id)
    data: dict[str, Any] = {
        "language": language,
        "format": project.format,
        "title": project.working_title,
        "packaging_promise": {
            "title_idea": str(promise.get("title_idea") or project.working_title)[:100],
            "thumbnail_text_idea": str(promise.get("thumbnail_text_idea") or "")[:40],
            "promise_statement": str(promise.get("promise_statement") or project.working_title)[:200],
        },
        "summary": str(brief.content.get("summary", ""))[:1200],
        "claims": claims[:40],
        "suggested_structure": brief.content.get("suggested_structure", [])[:10],
        "hook_ideas": brief.content.get("hook_ideas", [])[:5],
        "value_add": _value_add(db.get(OwnerValueAdd, project.id)),
        "target_duration_s": project.target_duration_s,
        "wpm": wpm,
        "recent_script_phrases": phrases,
    }
    claim_ids = {c["id"] for c in claims}

    def check(body: dict[str, Any]) -> list[craft.Finding]:
        return craft.check_script(
            body, fmt=project.format, target_duration_s=project.target_duration_s,  # type: ignore[arg-type]
            wpm=wpm, recent_phrases=tuple(phrases), claim_ids=claim_ids,
        )  # fmt: skip

    def draft(extra: dict[str, Any]) -> dict[str, Any]:
        out = run_agent(
            db, gateway, A11, {**data, **extra},
            channel_id=project.channel_id, project_id=project.id, idempotent=False, now=now,
        )  # fmt: skip
        if out.data is None:
            raise _outcome_error(out)
        return dict(out.data)

    asked = f"Owner's instruction for this draft: {instruction.strip()[:800]}" if instruction.strip() else ""
    if asked:
        latest = db.scalar(
            select(ScriptVersion)
            .join(Script, Script.id == ScriptVersion.script_id)
            .where(Script.project_id == project.id)
            .order_by(ScriptVersion.version.desc())
            .limit(1)
        )
        if latest is not None:
            data["current_draft"] = latest.plain_text[:40000]
    body = draft({"fix_notes": asked} if asked else {})
    findings = check(body)
    repaired = False
    if craft.errors(findings):
        log.info("script.repair", project_id=str(project.id), codes=[f.code for f in craft.errors(findings)])
        body = draft({"fix_notes": "; ".join(filter(None, [asked, _describe(findings)]))[:3000]})
        findings = check(body)
        repaired = True
    words, est = craft.measure(body, wpm)
    body = {**scripts.content(body), "word_count": words, "est_duration_s": est}  # measured by code
    script = db.scalar(select(Script).where(Script.project_id == project.id))
    if script is None:
        script = Script(id=uuid7(), project_id=project.id, channel_id=project.channel_id)
        db.add(script)
        db.flush()
    number = (
        db.scalar(
            select(func.coalesce(func.max(ScriptVersion.version), 0)).where(
                ScriptVersion.script_id == script.id
            )
        )
        or 0
    ) + 1
    info = scripts.summary(body, wpm)
    version = ScriptVersion(
        id=uuid7(),
        script_id=script.id,
        version=number,
        author_type="AGENT",
        author_id=A11.code,
        body=body,
        plain_text=info["plain_text"],
        word_count=info["word_count"],
        est_duration_s=info["est_duration_s"],
        content_sha256=info["content_sha256"],
    )
    db.add(version)
    db.flush()
    docs = _docs_for(db, [str(d["id"]) for d in brief.content.get("documents", [])])
    version.body = {**version.body, "_fact_check": "DONE" if docs else "NO_SOURCES"}
    if docs:
        _store_claims(
            db, project, "SCRIPT_VERSION", version.id,
            _fact_check(db, gateway, project, version.plain_text, docs, now), docs,
        )  # fmt: skip
    engine.transition(
        db, MACHINES["video_project"], project.id, "script_done", actor=Actor("AGENT", A11.code),
        payload={"script_done": True, "fact_check_done": bool(docs)},
        idempotency_key=f"script-done:{version.id}", now=now,
    )  # fmt: skip
    left = craft.errors(findings)
    notify_owners(
        db,
        event_type="script.ready",
        severity="WARNING" if left else "INFO",
        title="Script draft ready for review",
        body=(
            f"“{project.working_title}” v{number}: about {est} s."
            + (f" {len(left)} craft check(s) still need your edit." if left else " All craft checks pass.")
        ),
        dedup_key=f"script-ready:{version.id}",
        channel_id=project.channel_id,
        link=f"/projects/{project.id}/script",
        entity_type="video_project",
        entity_id=project.id,
    )
    db.commit()
    return ScriptResult(version, findings, repaired)


def fact_check_version(
    db: Session, gateway: Gateway, version_id: uuid.UUID, *, now: datetime | None = None
) -> int:
    """A10 on one script version (the owner's own edits). Marks ``_fact_check`` DONE; returns the
    number of claims found."""
    version = db.get_one(ScriptVersion, version_id)
    script = db.get_one(Script, version.script_id)
    project = db.get_one(VideoProject, script.project_id)
    brief = db.scalar(
        select(ResearchBrief)
        .where(ResearchBrief.project_id == project.id, ResearchBrief.status == "APPROVED")
        .order_by(ResearchBrief.version.desc())
        .limit(1)
    )
    docs = _docs_for(db, [str(d["id"]) for d in brief.content.get("documents", [])]) if brief else []
    rows: list[FactCheckClaim] = []
    if docs:
        outcome = _fact_check(db, gateway, project, version.plain_text, docs, now)
        rows = _store_claims(db, project, "SCRIPT_VERSION", version.id, outcome, docs)
    version.body = {**version.body, "_fact_check": "DONE" if docs else "NO_SOURCES"}
    db.commit()
    return len(rows)
