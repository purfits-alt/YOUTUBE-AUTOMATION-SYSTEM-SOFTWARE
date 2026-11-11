"""Discovery pipelines and API with a scripted model (CHANNEL_DISCOVERY_SPEC §2–§6, §9)."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from tubeforge_agents import discovery as pipe

from tests.integration.conftest import Env, login
from tests.unit import discovery_fixtures as fx
from tests.unit.test_research_fetcher import resolver
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    AgentRun,
    Channel,
    ChannelStrategy,
    Keyword,
    NicheCandidate,
    NicheReport,
    SystemSettings,
)
from tubeforge.gateway.adapters import TextRequest, TextResponse
from tubeforge.gateway.core import Gateway
from tubeforge.research.fetcher import ResearchFetcher
from tubeforge.research.scoring import score
from tubeforge.secrets import MemoryStore, SecretBox

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
DOC_ID = re.compile(r'<untrusted_source id="([0-9a-f-]{36})"')
Reply = Callable[[TextRequest, list[str]], dict[str, Any]]


class ScriptedModel:
    """Local 'model' (keyless, like Ollama) answering per agent; sees the document ids it was given."""

    family = "ollama"
    hosts: frozenset[str] = frozenset()
    needs_key = False

    def __init__(self) -> None:
        self.replies: dict[str, Reply] = {}
        self.calls: list[tuple[str, TextRequest]] = []

    def text(self, request: TextRequest, api_key: str | None) -> TextResponse:
        code = re.search(r"\((A\d\d_[A-Z_]+) v", request.system or "")
        agent = code.group(1) if code else "?"
        self.calls.append((agent, request))
        user = request.messages[-1].content
        return TextResponse(json.dumps(self.replies[agent](request, DOC_ID.findall(user))), 400, 300)


def views(req: httpx.Request) -> httpx.Response:
    m = re.search(r"/per-article/[^/]+/all-access/user/([^/]+)/daily/(\d{8})00/(\d{8})00", req.url.path)
    if not m:
        return httpx.Response(404)
    start, end = (datetime.strptime(x, "%Y%m%d").date() for x in m.group(2, 3))
    days = (end - start).days + 1
    spike = m.group(1) == "Budgeting"
    items = [
        {
            "timestamp": f"{start + timedelta(days=i):%Y%m%d}00",
            "views": 400 if spike and i >= days - 7 else 100,
        }
        for i in range(days)
    ]
    return httpx.Response(200, json={"items": items})


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine = create_engine(env.db_url)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


@pytest.fixture
def model() -> ScriptedModel:
    return ScriptedModel()


@pytest.fixture
def gw(model: ScriptedModel) -> Gateway:
    box = SecretBox(MemoryStore())
    box.ensure_master_key()
    return Gateway(box, adapters={"ollama": model})  # type: ignore[dict-item]


@pytest.fixture
def fetched() -> list[str]:
    return []


@pytest.fixture
def fetcher(fetched: list[str]) -> Iterator[ResearchFetcher]:
    def handler(req: httpx.Request) -> httpx.Response:
        fetched.append(str(req.url))
        return views(req)

    with ResearchFetcher(
        transport=httpx.MockTransport(handler),
        resolver=resolver({"wikimedia.org": ["185.15.59.224"]}),
        contact="",
    ) as f:
        yield f


def a02_reply(_req: TextRequest, ids: list[str]) -> dict[str, Any]:
    good = {"source_document_id": ids[0], "quote": "Average per day: 100.0"}
    return {
        "candidates": [
            {
                "name": "Student budgets with real numbers",
                "summary": "Explainers using the owner's own monthly budget.",
                "language": "en",
                "criteria": [
                    {"code": "AUDIENCE_DEMAND", "value": 70, "evidence": [good], "confidence": "MEDIUM"},
                    {"code": "EVERGREEN", "value": 80, "evidence": [good], "confidence": "HIGH"},
                    {"code": "PRODUCTION_FEASIBILITY_H-LITE", "value": 90, "evidence": [],
                     "confidence": "HIGH"},
                    {"code": "COMPETITION_LEVEL", "value": 50, "evidence": [], "confidence": "LOW",
                     "note": "no direct evidence"},
                ],
                "inauthentic_risk": "MEDIUM",
                "production_difficulty": "LOW",
                "originality_angles": ["Owner shares their own budget"],
            },
            {
                "name": "Home cooking on a budget",
                "summary": "Cheap meals, cooked and costed by the owner.",
                "language": "en",
                "criteria": [
                    {"code": "AUDIENCE_DEMAND", "value": 60, "evidence": [
                        {"source_document_id": "00000000-0000-0000-0000-000000000000", "quote": "invented"}
                    ], "confidence": "HIGH"},
                ],
                "inauthentic_risk": "LOW",
                "production_difficulty": "LOW",
            },
            {"name": "Crypto trading signals", "summary": "Daily coin picks.", "language": "en",
             "criteria": [{"code": "AUDIENCE_DEMAND", "value": 90, "evidence": [], "confidence": "LOW"}],
             "inauthentic_risk": "HIGH", "production_difficulty": "LOW"},
            {"name": "Side hustles", "summary": "A guaranteed way to earn online.", "language": "en",
             "criteria": [{"code": "AUDIENCE_DEMAND", "value": 90, "evidence": [], "confidence": "LOW"}],
             "inauthentic_risk": "HIGH", "production_difficulty": "LOW"},
            {"name": "Recetas baratas", "summary": "Cocina barata.", "language": "es",
             "criteria": [{"code": "AUDIENCE_DEMAND", "value": 90, "evidence": [], "confidence": "LOW"}],
             "inauthentic_risk": "LOW", "production_difficulty": "LOW"},
        ]
    }  # fmt: skip


def report(db: Session, env: Env, **params: Any) -> NicheReport:
    row = NicheReport(
        id=uuid7(),
        requested_by=env.owner.id,
        params={"languages": ["en"], "interests": [], "avoid": ["crypto"], **params},
        status="QUEUED",
    )
    db.add(row)
    db.commit()
    return row


def test_let_tubeforge_suggest_discovery_end_to_end(
    db: Session, env: Env, gw: Gateway, model: ScriptedModel, fetcher: ResearchFetcher, fetched: list[str]
) -> None:
    model.replies["A02_NICHE_DISCOVERY"] = a02_reply
    rep = report(db, env, avoid=["crypto", "Chess"])
    out = pipe.run_discovery(db, gw, fetcher, rep.id, now=NOW)
    assert out.status == "DONE", out.params
    result = out.params["result"]
    # 24 suggestion topics minus 'Chess' (avoid list) → 23 pageview series, one year each
    assert len(fetched) == 23 and result["documents"] == 23
    assert all("/user/" in u and u.endswith("/2025111000/2026110900") for u in fetched)
    assert sorted(result["dropped"]) == [
        "Crypto trading signals: matches the avoid list",
        "Recetas baratas: language es was not requested",
        "Side hustles: forbidden phrase 'guaranteed'",
    ]
    cands = {c.name: c for c in db.scalars(select(NicheCandidate).where(NicheCandidate.report_id == rep.id))}
    assert set(cands) == {"Student budgets with real numbers", "Home cooking on a budget"}
    good = {c["code"]: c for c in cands["Student budgets with real numbers"].criteria}
    assert good["AUDIENCE_DEMAND"]["confidence"] == "MEDIUM" and good["AUDIENCE_DEMAND"]["evidence"][0][
        "url"
    ].startswith("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/")
    assert good["PRODUCTION_FEASIBILITY"]["confidence"] == "LOW"  # uncited HIGH → downgraded
    assert good["_ORIGINALITY_ANGLES"]["angles"] == ["Owner shares their own budget"]
    cooking = cands["Home cooking on a budget"].criteria[0]
    assert cooking["confidence"] == "LOW" and cooking["evidence"] == []  # invented document id removed
    crit = [c for c in cands["Student budgets with real numbers"].criteria if not c["code"].startswith("_")]
    weights = {c["code"]: c["weight"] for c in crit}
    assert cands["Student budgets with real numbers"].opportunity_score == score(crit, weights).value
    # the prompt carried the metrics and fenced every document; no YouTube data is involved
    (_agent, req), = model.calls  # fmt: skip
    user = req.messages[-1].content
    assert user.count("<untrusted_source id=") == 23 + 3 and '"demand_hint"' in user
    assert "youtube.com" not in user
    run = db.get_one(AgentRun, out.agent_run_id)
    assert run.agent_code == "A02_NICHE_DISCOVERY" and run.status == "SUCCEEDED"


def test_discovery_respects_emergency_stop_and_reports_waiting_quota(
    db: Session, env: Env, gw: Gateway, model: ScriptedModel, fetcher: ResearchFetcher, fetched: list[str]
) -> None:
    db.get_one(SystemSettings, 1).emergency_stop = True
    db.commit()
    stopped = pipe.run_discovery(db, gw, fetcher, report(db, env).id, now=NOW)
    assert stopped.status == "STOPPED" and fetched == [] and model.calls == []
    db.get_one(SystemSettings, 1).emergency_stop = False
    db.execute(
        AgentRun.__table__.insert(),
        [
            {"id": uuid7(), "agent_code": "A02_NICHE_DISCOVERY", "input_sha256": "x" * 64, "input": {},
             "status": "SUCCEEDED", "started_at": NOW}
            for _ in range(30)
        ],
    )  # fmt: skip
    db.commit()
    waiting = pipe.run_discovery(db, gw, fetcher, report(db, env, interests=["Budget"]).id, now=NOW)
    assert waiting.status == "WAITING_QUOTA" and "Daily budget" in waiting.params["result"]["error"]
    assert model.calls == []
    again = pipe.run_discovery(db, gw, fetcher, waiting.id, now=NOW)  # a re-run is allowed later
    assert again.status == "WAITING_QUOTA"


def _shortlisted(db: Session, env: Env, **kw: Any) -> NicheCandidate:
    rep = report(db, env)
    rep.status = "DONE"
    cand = NicheCandidate(
        id=uuid7(),
        report_id=rep.id,
        name=kw.get("name", "Student budgets"),
        summary="Real student budgets.",
        language="en",
        criteria=[
            {"code": "AUDIENCE_DEMAND", "value": 70, "weight": 8.0, "confidence": "LOW", "evidence": []}
        ],
        opportunity_score=Decimal("70.00"),
        inauthentic_risk="MEDIUM",
        production_difficulty="LOW",
        status=kw.get("status", "SHORTLISTED"),
    )
    db.add(cand)
    db.commit()
    return cand


def test_blueprint_draft_from_a06_and_a07(db: Session, env: Env, gw: Gateway, model: ScriptedModel) -> None:
    strategy = fx.strategy()
    strategy["ideas"][7] = {**strategy["ideas"][6], "title": strategy["ideas"][6]["title"] + "."}  # near-dup
    model.replies["A07_CHANNEL_BRANDING"] = lambda _r, _ids: fx.branding()
    model.replies["A06_CHANNEL_STRATEGY"] = lambda _r, _ids: strategy
    cand = _shortlisted(db, env)
    result = pipe.generate_blueprint(db, gw, cand.id, owner_notes="I study economics.", now=NOW)
    row = db.get_one(ChannelStrategy, result.strategy.id)
    assert (row.status, row.version, row.channel_id) == ("DRAFT", 1, None)
    assert result.problems == [], result.problems
    b = row.blueprint
    assert (
        len(b["ideas"]) == 50 and len(b["name_ideas"]) == 10 and b["brand"]["contrast_pair"]["ratio"] >= 4.5
    )
    assert all(e["idea_ref"] < 50 for e in b["calendar_30d"])
    a06 = next(r for a, r in model.calls if a == "A06_CHANNEL_STRATEGY")
    assert "I study economics." in a06.messages[-1].content and "H-LITE" in (a06.system or "")
    second = pipe.generate_blueprint(db, gw, cand.id, now=NOW)
    assert second.strategy.version == 2

    model.replies["A07_CHANNEL_BRANDING"] = lambda _r, _ids: {
        **fx.branding(),
        "description": "Guaranteed to grow fast, join now and watch the numbers.",
    }
    other = _shortlisted(db, env, name="Cheap student meals")  # new prompt: the Gateway cache does not answer
    with pytest.raises(pipe.PipelineError, match="Forbidden phrase"):
        pipe.generate_blueprint(db, gw, other.id, now=NOW)
    assert (
        db.scalar(
            select(func.count())
            .select_from(ChannelStrategy)
            .where(ChannelStrategy.niche_candidate_id == other.id)
        )
        == 0
    )
    with pytest.raises(pipe.PipelineError, match="Shortlist"):
        pipe.generate_blueprint(db, gw, _shortlisted(db, env, status="NEW").id, now=NOW)


def _active_channel(db: Session, pillars: list[str]) -> Channel:
    ch = Channel(id=uuid7(), name="Budget Lab", state="ACTIVE", content_language="en")
    db.add(ch)
    db.flush()
    bp_json = {"pillars": [{"name": p, "description": p} for p in pillars]}
    db.add(ChannelStrategy(id=uuid7(), channel_id=ch.id, version=1, status="APPROVED", blueprint=bp_json))
    db.commit()
    return ch


def test_trend_scan_keeps_code_strength_and_clamps_expiry(
    db: Session, gw: Gateway, model: ScriptedModel, fetcher: ResearchFetcher
) -> None:
    ch = _active_channel(db, ["Budgeting", "Cooking"])

    def a03(_req: TextRequest, ids: list[str]) -> dict[str, Any]:
        return {
            "items": [
                {"topic": "Budgeting interest jumps", "summary": "Pageviews rose this week.",
                 "source_document_ids": [ids[0]], "signal_strength": 99, "confidence": "MEDIUM",
                 "expires_at": "2027-12-31T00:00:00Z", "pillar": "Budgeting"},
                {"topic": "Invented", "summary": "No real source.", "source_document_ids": ["nope"],
                 "signal_strength": 5, "confidence": "HIGH", "expires_at": "2026-11-12T00:00:00Z",
                 "pillar": "Cooking"},
            ]
        }  # fmt: skip

    model.replies["A03_TREND_INTELLIGENCE"] = a03
    items = pipe.run_trend_scan(db, gw, fetcher, ch.id, now=NOW)
    assert [i.topic for i in items] == ["Budgeting interest jumps"]
    item = items[0]
    assert item.signal_strength == Decimal("300.00")  # z-score from code, not the model's 99
    assert item.expires_at == NOW + timedelta(days=60)
    (_a, req), = model.calls  # fmt: skip
    assert '"Cooking"' in req.messages[-1].content or "Cooking" in (req.system or "")
    assert "Budgeting" in req.messages[-1].content  # only the strong signal (Cooking is flat) is sent
    assert pipe.run_trend_scan(db, gw, fetcher, _active_channel(db, []).id, now=NOW) == []


def test_keywords_drop_invented_volumes_and_upsert(db: Session, gw: Gateway, model: ScriptedModel) -> None:
    ch = _active_channel(db, ["Budgeting"])
    model.replies["A05_KEYWORD_RESEARCH"] = lambda _r, _ids: {
        "items": [
            {"phrase": "how to make a student budget in excel", "intent": "HOW_TO",
             "rationale": "Common how-to form", "evidence": [], "confidence": "LOW"},
            {"phrase": "student budget app", "intent": "COMPARE",
             "rationale": "About 12k searches per month", "evidence": [], "confidence": "MEDIUM"},
            {"phrase": "guaranteed savings", "intent": "LEARN", "rationale": "x", "evidence": [],
             "confidence": "LOW"},
        ]
    }  # fmt: skip
    saved = pipe.run_keywords(db, gw, ch.id, ["student budget"], now=NOW)
    assert [k.phrase for k in saved] == ["how to make a student budget in excel"]
    pipe.run_keywords(db, gw, ch.id, ["student budget"], now=NOW)
    n = db.scalar(select(func.count()).select_from(Keyword).where(Keyword.channel_id == ch.id))
    assert n == 1 and saved[0].notes and saved[0].notes.startswith("HOW_TO · LOW confidence")


# -------------------------------------------------------------------------------------------- API
def test_niches_api(env: Env, db: Session) -> None:
    cand = _shortlisted(db, env)
    with env.client() as client:
        h = login(client)
        idem = {**h, "Idempotency-Key": str(uuid.uuid4())}
        r = client.post("/api/v1/niches/reports", json={"avoid": ["crypto"]}, headers=idem)
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "QUEUED" and r.json()["languages"] == ["en"]
        assert (
            client.post("/api/v1/niches/reports", json={"avoid": ["crypto"]}, headers=idem).json()["id"]
            == r.json()["id"]
        )
        jobs = env.sql("SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%research.discover'")
        assert len(jobs) == 1 and jobs[0][0]["report_id"] == r.json()["id"]
        bad = client.post(
            "/api/v1/niches/reports",
            json={"interests": ["<script>"]},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert bad.status_code in (400, 422)

        detail = client.get(f"/api/v1/niches/reports/{cand.report_id}").json()
        assert detail["candidates_list"][0]["footer"].startswith("Estimates based on cited sources")
        profiles = {p["name"]: p for p in client.get("/api/v1/niches/weight-profiles").json()}
        assert (
            profiles["Balanced"]["is_default"]
            and profiles["Originality-first"]["weights"]["INAUTHENTIC_RISK_INVERSE"] == 15
        )
        r = client.post(
            "/api/v1/niches/rescore",
            json={"report_id": str(cand.report_id), "weights": {"AUDIENCE_DEMAND": 3}},
            headers=h,
        )
        assert r.status_code == 200 and r.json()[0]["criteria"][0]["weight"] == 3.0
        r = client.post(
            "/api/v1/niches/rescore",
            json={"report_id": str(cand.report_id), "weights": {"VIEWS": 3}},
            headers=h,
        )
        assert (r.status_code, r.json()["code"]) == (422, "INVALID_WEIGHTS")
        r = client.post(
            "/api/v1/niches/rescore",
            json={"report_id": str(cand.report_id), "weight_profile_id": profiles["Originality-first"]["id"]},
            headers=h,
        )
        assert r.status_code == 200
        new = client.post(
            "/api/v1/niches/weight-profiles",
            json={"name": "Mine", "weights": {"EVERGREEN": 10}, "is_default": True},
            headers=h,
        )
        assert new.status_code == 201 and new.json()["is_default"]
        again = client.post("/api/v1/niches/weight-profiles", json={"name": "Mine", "weights": {}}, headers=h)
        assert again.json()["code"] == "DUPLICATE_PROFILE"
        defaults = [p for p in client.get("/api/v1/niches/weight-profiles").json() if p["is_default"]]
        assert [p["name"] for p in defaults] == ["Mine"]

        assert (
            client.post(f"/api/v1/niches/candidates/{cand.id}/commands/dismiss", headers=h).json()["status"]
            == "DISMISSED"
        )
        r = client.post(
            "/api/v1/strategies",
            json={"niche_candidate_id": str(cand.id)},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert (r.status_code, r.json()["code"]) == (409, "NOT_SHORTLISTED")
        client.post(f"/api/v1/niches/candidates/{cand.id}/commands/shortlist", headers=h)
        r = client.post(
            "/api/v1/strategies",
            json={"niche_candidate_id": str(cand.id)},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 202 and r.json()["status"] == "QUEUED"

        env.sql("UPDATE system_settings SET emergency_stop = true")
        r = client.post(
            "/api/v1/niches/reports", json={}, headers={**h, "Idempotency-Key": str(uuid.uuid4())}
        )
        assert (r.status_code, r.json()["code"]) == (409, "STOPPED")
        env.sql("UPDATE system_settings SET emergency_stop = false")

        row = ChannelStrategy(
            id=uuid7(), niche_candidate_id=cand.id, version=1, status="DRAFT",
            blueprint={"schema_version": 1}, channel_id=None,
        )  # fmt: skip
        db.add(row)
        db.commit()
        got = client.get(f"/api/v1/strategies/{row.id}").json()
        assert got["status"] == "DRAFT" and got["problems"] and got["problems"][0].startswith("Schema /")
        assert [s["id"] for s in client.get(f"/api/v1/strategies?niche_candidate_id={cand.id}").json()] == [
            str(row.id)
        ]
    actions = {a for (a,) in env.sql("SELECT action FROM audit_log")}
    assert {"niche_report.started", "niche_report.rescored", "weight_profile.created", "blueprint.requested",
            "niche_candidate.shortlist", "niche_candidate.dismiss"} <= actions  # fmt: skip


def test_viewer_can_read_but_not_run(env: Env, add_user) -> None:  # type: ignore[no-untyped-def]
    add_user("viewer2@example.com", "VIEWER")
    with env.client() as client:
        h = login(client, "viewer2@example.com")
        r = client.post(
            "/api/v1/niches/reports", json={}, headers={**h, "Idempotency-Key": str(uuid.uuid4())}
        )
        assert r.status_code == 403
        assert client.post("/api/v1/strategies", json={"niche_candidate_id": str(uuid.uuid4())},
                           headers={**h, "Idempotency-Key": str(uuid.uuid4())}
                           ).status_code == 403  # fmt: skip
