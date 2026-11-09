"""Orchestrator (WORKFLOW_STATE_MACHINE §10): every transition of every machine.

- table-driven: each edge from each source state succeeds with its guards satisfied, and is refused
  with each guard violated on its own;
- every (state, event) pair not in the table is refused;
- Emergency Stop refuses everything except pause/cancel and the safety moves;
- idempotency, actor rules, mode gates, universal pause/resume/cancel/fail/retry;
- approvals bound to a hash; reconciler (lost and stalled jobs, exactly once); property tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from tests.integration.conftest import Env
from tubeforge.audit import Actor
from tubeforge.db.ids import uuid7
from tubeforge.db.models import (
    ApprovalRequest,
    AssetRights,
    Channel,
    ChannelPublishingRules,
    MediaAsset,
    Notification,
    NotificationDelivery,
    OAuthClient,
    OAuthConnection,
    RenderJob,
    StockPurchase,
    SystemSettings,
    UploadJob,
    VideoIdea,
    VideoProject,
    VoiceProfile,
    WorkflowTransition,
)
from tubeforge.orchestrator import approvals, engine, reconciler
from tubeforge.orchestrator.engine import TransitionRejected
from tubeforge.orchestrator.machines import MACHINES, PROJECT, Edge, Machine
from tubeforge.queue import defer_in_transaction

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
SHA_A, SHA_B = "a" * 64, "b" * 64


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine_ = create_engine(env.db_url)
    with Session(engine_, expire_on_commit=False) as session:
        yield session
    engine_.dispose()


# ------------------------------------------------------------------------------------- factories
@dataclass
class W:
    db: Session
    owner_id: uuid.UUID
    channel: Channel

    def actor(self, kind: str) -> Actor:
        return {
            "OWNER": Actor("OWNER", str(self.owner_id)),
            "ORCH": Actor("ORCH", "orchestrator"),
            "AGENT": Actor("AGENT", "a01"),
            "AUDITOR": Actor("AUDITOR", "a21"),
            "SYSTEM": Actor("SYSTEM", "system"),
        }[kind]


def world(db: Session, env: Env) -> W:
    channel = Channel(
        id=uuid7(), name="Orch channel", state="ACTIVE", content_language="en", private_only_mode=False
    )
    db.add(channel)
    db.flush()
    db.add(ChannelPublishingRules(channel_id=channel.id))
    db.flush()
    return W(db, env.owner.id, channel)


def _project(w: W, state: str = "IDEA", **kw: Any) -> VideoProject:
    p = VideoProject(
        id=uuid7(),
        channel_id=w.channel.id,
        format=kw.pop("format", "LONG"),
        state=state,
        working_title="Orch project",
        target_duration_s=600,
        render_profile={},
        **kw,
    )
    w.db.add(p)
    w.db.flush()
    return p


def _asset(w: W, project: VideoProject | None, kind: str = "IMAGE") -> MediaAsset:
    a = MediaAsset(
        id=uuid7(),
        channel_id=w.channel.id,
        project_id=project.id if project else None,
        kind=kind,
        mime_type="image/png",
        size_bytes=1,
        sha256=SHA_A,
        origin="PROCEDURAL",
        retention_class="CACHE",
        created_by_type="SYSTEM",
        created_by_id="system",
    )
    w.db.add(a)
    w.db.flush()
    return a


def _approval(
    w: W, subject_type: str, subject_id: uuid.UUID, state: str = "PENDING", sha: str = SHA_A
) -> ApprovalRequest:
    a = ApprovalRequest(
        id=uuid7(),
        channel_id=w.channel.id,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_sha256=sha,
        state=state,
        requested_by_type="SYSTEM",
        expires_at=NOW + timedelta(days=14),
    )
    w.db.add(a)
    w.db.flush()
    return a


def make(w: W, machine: Machine, state: str) -> Any:
    db = w.db
    t = machine.entity_type
    if t == "channel":
        ch = Channel(id=uuid7(), name="C", state=state, content_language="en", private_only_mode=False)
        db.add(ch)
        db.flush()
        return ch
    if t == "video_idea":
        idea = VideoIdea(
            id=uuid7(),
            channel_id=w.channel.id,
            state=state,
            title="Bridges",
            angle="maths",
            format="LONG",
            source="OWNER",
        )
        db.add(idea)
        db.flush()
        return idea
    if t == "video_project":
        return _project(w, state)
    if t == "render_job":
        p = _project(w, "RENDERING")
        tv = uuid7()
        db.execute(
            text(
                "INSERT INTO timeline_versions (id, project_id, channel_id, version, schema_version,"
                " timeline, content_sha256, created_by_type, created_by_id)"
                " VALUES (:i, :p, :c, 1, '1', '{}', :h, 'SYSTEM', 's')"
            ),
            {"i": tv, "p": p.id, "c": w.channel.id, "h": SHA_A},
        )
        r = RenderJob(
            id=uuid7(),
            project_id=p.id,
            channel_id=w.channel.id,
            timeline_version_id=tv,
            kind="FINAL",
            state=state,
            preset={},
            idempotency_key=str(uuid7()),
        )
        db.add(r)
        db.flush()
        return r
    if t == "upload_job":
        p = _project(w, "UPLOADING")
        a = _asset(w, p, "RENDER_FINAL")
        ap = _approval(w, "UPLOAD_PACKAGE", p.id, "APPROVED")
        j = UploadJob(
            id=uuid7(),
            project_id=p.id,
            channel_id=w.channel.id,
            approval_request_id=ap.id,
            file_asset_id=a.id,
            file_sha256=uuid7().hex + uuid7().hex,
            state=state,
            privacy_status="private",
            made_for_kids=False,
            contains_synthetic_media=False,
            bytes_total=1,
            is_test=True,
        )
        db.add(j)
        db.flush()
        return j
    if t == "notification_delivery":
        n = Notification(
            id=uuid7(),
            user_id=w.owner_id,
            event_type="t",
            severity="INFO",
            title="t",
            body="b",
            dedup_key=str(uuid7()),
        )
        db.add(n)
        db.flush()
        d = NotificationDelivery(id=uuid7(), notification_id=n.id, channel="IN_APP", state=state)
        db.add(d)
        db.flush()
        return d
    if t == "approval_request":
        return _approval(w, "SCRIPT", uuid7(), state)
    if t == "voice_profile":
        v = VoiceProfile(
            id=uuid7(), owner_user_id=w.owner_id, label="Mine", state=state, engine="OPENVOICE_V2"
        )
        db.add(v)
        db.flush()
        return v
    if t == "stock_purchase":
        s = StockPurchase(
            id=uuid7(),
            channel_id=w.channel.id,
            provider_code="pexels",
            provider_asset_id="1",
            state=state,
            licence_type="standard",
            price_minor=500,
            currency="USD",
            quoted_at=NOW,
        )
        db.add(s)
        db.flush()
        return s
    raise AssertionError(t)


# ------------------------------------------------------------------------- guard fixtures (good/bad)
@dataclass
class Case:
    w: W
    entity: Any
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str = "OWNER"
    expect: str = "GUARD_FAILED"

    @property
    def db(self) -> Session:
        return self.w.db

    def settings(self) -> SystemSettings:
        return self.db.get_one(SystemSettings, 1)

    def rules(self) -> ChannelPublishingRules:
        return self.db.get_one(ChannelPublishingRules, self.w.channel.id)

    def go_auto(self) -> None:
        """The orchestrator acting under accepted auto rules in FULLY-AUTOMATIC mode."""
        self.actor = "ORCH"
        self.w.channel.operating_mode = "FULLY_AUTOMATIC"
        self.payload["auto_rule_id"] = "rule-1"
        self.db.flush()


Fix = Callable[[Case], None]
QC_OK = {
    "duration_delta_s": 0.0,
    "streams_ok": True,
    "resolution_ok": True,
    "loudness_delta_lu": 0.2,
    "black_or_frozen_s": 0,
    "silence_gap_s": 0,
}
AUDITS_OK = [
    {"kind": k, "status": "PASSED"} for k in ("CONTENT", "COPYRIGHT", "POLICY", "QUALITY", "THUMBNAIL")
]
CHOICES = {
    "privacy_status": "private",
    "made_for_kids": False,
    "contains_synthetic_media": False,
    "thumbnail_id": "t1",
    "title": "A title",
}


def _connection(c: Case) -> None:
    client = OAuthClient(id=uuid7(), label="x", client_id="1-a.apps.googleusercontent.com")
    c.db.add(client)
    c.db.flush()
    c.db.add(
        OAuthConnection(
            id=uuid7(),
            channel_id=c.entity.id,
            oauth_client_id=client.id,
            scopes=[],
            refresh_token_enc=b"x",
            key_id="k",
            status="ACTIVE",
            authorized_at=NOW,
        )
    )
    c.db.flush()


def _set(**kw: Any) -> Fix:
    def fix(c: Case) -> None:
        for k, v in kw.items():
            setattr(c.entity, k, v)
        c.db.flush()

    return fix


def _pay(**kw: Any) -> Fix:
    return lambda c: c.payload.update(kw)


def _upload_approval(sha: str) -> Fix:
    def fix(c: Case) -> None:
        ap = _approval(c.w, "UPLOAD_PACKAGE", c.entity.id, "APPROVED", SHA_A)
        c.payload.update(approval_request_id=str(ap.id), package_sha256=sha, current_package_sha256=sha)

    return fix


def _cut_approval(sha: str) -> Fix:
    def fix(c: Case) -> None:
        _approval(c.w, "ROUGH_CUT", c.entity.id, "APPROVED", SHA_A)
        c.payload["timeline_sha256"] = sha

    return fix


def _seq(*fixes: Fix) -> Fix:
    def fix(c: Case) -> None:
        for f in fixes:
            f(c)

    return fix


def _unrighted_asset(c: Case) -> None:
    c.payload["scenes_without_visual"] = 0
    _asset(c.w, c.entity, "IMAGE")


def _qc_loops(c: Case) -> None:
    for _ in range(2):
        c.db.add(
            WorkflowTransition(
                entity_type="video_project",
                entity_id=c.entity.id,
                from_state="RENDERING",
                to_state="ASSEMBLY",
                event="qc_failed_fixable",
                actor_type="ORCH",
                actor_id="o",
                idempotency_key=str(uuid7()),
            )
        )
    c.db.flush()


def _rights_written(c: Case) -> None:
    a = _asset(c.w, None, "VIDEO_CLIP")
    c.db.add(
        AssetRights(
            asset_id=a.id, rights_basis="STOCK_PAID_LICENCE", licence_name="x", commercial_use_allowed=True
        )
    )
    c.entity.asset_id = a.id
    c.db.flush()


def _blocked_topic(c: Case) -> None:
    c.rules().blocked_topics = ["crypto"]
    c.entity.title = "Crypto news today"
    c.db.flush()


def _setting(**kw: Any) -> Fix:
    def fix(c: Case) -> None:
        c.settings().settings = {**(c.settings().settings or {}), **kw}
        c.db.flush()

    return fix


GOOD: dict[str, Fix] = {
    "channel_ready_to_activate": _set(
        successful_private_test_uploads=1, privacy_policy_url="https://x.example/p"
    ),
    "oauth_healthy": _connection,
    "channel_active": lambda c: None,
    "publishing_switch_off": _pay(privacy_status="private"),
    "orch_discard_only_expired": _set(expires_at=NOW - timedelta(hours=1)),
    "has_calendar_date": _set(calendar_date=date(2026, 11, 1)),
    "idea_original": _set(similarity_max=Decimal("0.2")),
    "topic_allowed": lambda c: None,
    "calendar_date_reached_if_auto": _set(calendar_date=date(2026, 11, 1)),
    "research_and_fact_check_done": _pay(research_done=True, fact_check_done=True),
    "research_brief_valid": _pay(claims=[{"sources": 2, "verdict": "supported"}]),
    "script_and_fact_check_done": _pay(script_done=True, fact_check_done=True),
    "script_locked": _pay(script_version_locked=True),
    "no_contradicted_claims": _pay(contradicted_claims=0),
    "owner_value_add": _pay(value_add_fields=2),
    "duration_fits_format": _pay(estimated_duration_s=420),
    "scenes_have_rights_cleared_visuals": _pay(scenes_without_visual=0),
    "narration_complete": _pay(scenes_without_narration=0),
    "voice_consent_valid": _pay(voice_source="owner_recording"),
    "timeline_and_proxy_ready": _pay(timeline_version_id="tv1", proxy_ready=True),
    "cut_version_approved": _cut_approval(SHA_A),
    "external_editor_enabled": _setting(external_editors=["davinci"]),
    "reimport_declared": _pay(declaration={"app": "x", "plan": "free", "assets": [], "ai_content": False}),
    "qc_passed": _pay(qc=QC_OK),
    "qc_loops_left": lambda c: None,
    "package_complete": _pay(
        thumbnails_passing=3,
        title="A title",
        chapters_valid=True,
        captions_synced=True,
        contains_synthetic_media=False,
        synthetic_reason="no realistic AI",
    ),
    "critical_audit_failure": _pay(audits=[{"kind": "QUALITY", "status": "FAILED", "critical": True}]),
    "audits_pass_thresholds": _pay(audits=AUDITS_OK, originality_score=90, caps_ok=True),
    "override_reason": _pay(override_reason="Checked by hand, the flagged clip is my own."),
    "no_copyright_critical": lambda c: None,
    "publish_choices_explicit": _pay(**CHOICES),
    "private_only_respected": _pay(privacy_status="private"),
    "schedule_rules": lambda c: None,
    "approval_hash_recorded": _upload_approval(SHA_A),
    "approval_hash_current": _upload_approval(SHA_A),
    "has_video_id": _pay(youtube_video_id="vid1"),
    "all_segments_done": _set(segments_total=2, segments_done=2),
    "render_attempts_left": _set(attempt=1),
    "is_test_upload": lambda c: None,
    "subject_hash_matches": lambda c: c.payload.update(subject_sha256=c.entity.subject_sha256),
    "auto_rule_recorded_if_auto": lambda c: None,
    "auto_allowed_for_subject": lambda c: None,
    "has_comment": _pay(comment="Shorter intro please"),
    "enough_sample_minutes": _set(sample_seconds=Decimal(200)),
    "live_consent_recorded": _pay(consent_audio_asset_id="a1", one_time_code="482913"),
    "voice_verification_passed": _pay(stt_code_match=True, speaker_similarity=0.9),
    "within_budget": _pay(budget_remaining_minor=10_000),
    "stock_provider_enabled": _pay(provider_enabled=True),
    "licence_fits_channel": lambda c: None,
    "rights_record_written": _rights_written,
}

BAD: dict[str, Fix] = {
    "channel_ready_to_activate": _set(successful_private_test_uploads=0),
    "oauth_healthy": lambda c: c.db.execute(text("DELETE FROM oauth_connections")),
    "channel_active": lambda c: (setattr(c.w.channel, "state", "PAUSED"), c.db.flush()),
    "publishing_switch_off": lambda c: (
        c.payload.update(privacy_status="public"),
        setattr(c.settings(), "publishing_kill_switch", True),
        c.db.flush(),
    ),
    "orch_discard_only_expired": lambda c: (
        setattr(c.entity, "expires_at", NOW + timedelta(days=3)),
        setattr(c, "actor", "ORCH"),
        c.db.flush(),
    ),
    "has_calendar_date": _set(calendar_date=None),
    "idea_original": _set(similarity_max=Decimal("0.95")),
    "topic_allowed": _blocked_topic,
    "calendar_date_reached_if_auto": lambda c: (
        c.go_auto(),
        setattr(c.entity, "calendar_date", date(2030, 1, 1)),
        c.db.flush(),
    ),
    "research_and_fact_check_done": _pay(fact_check_done=False),
    "research_brief_valid": _pay(claims=[{"sources": 0}]),
    "script_and_fact_check_done": _pay(script_done=False),
    "script_locked": _pay(script_version_locked=False),
    "no_contradicted_claims": _pay(contradicted_claims=2),
    "owner_value_add": _pay(value_add_fields=0),
    "duration_fits_format": lambda c: (
        c.payload.update(estimated_duration_s=400),
        setattr(c.entity, "format", "SHORT"),
        c.db.flush(),
    ),
    "scenes_have_rights_cleared_visuals": _unrighted_asset,
    "narration_complete": _pay(scenes_without_narration=3),
    "voice_consent_valid": _pay(voice_source="owner_clone", voice_profile_id=str(uuid7())),
    "timeline_and_proxy_ready": _pay(proxy_ready=False),
    "cut_version_approved": _cut_approval(SHA_B),
    "external_editor_enabled": _setting(external_editors=[]),
    "reimport_declared": _pay(declaration={"app": "x"}),
    "qc_passed": _pay(qc={**QC_OK, "loudness_delta_lu": 3.0}),
    "qc_loops_left": _qc_loops,
    "package_complete": _pay(thumbnails_passing=1),
    "critical_audit_failure": _pay(audits=[]),
    "audits_pass_thresholds": _pay(originality_score=10),
    "override_reason": _pay(override_reason="too short"),
    "no_copyright_critical": _pay(audits=[{"kind": "COPYRIGHT", "status": "FAILED", "critical": True}]),
    "publish_choices_explicit": lambda c: c.payload.pop("made_for_kids", None),
    "private_only_respected": lambda c: (
        setattr(c.w.channel, "private_only_mode", True),
        c.payload.update(privacy_status="unlisted"),
        c.db.flush(),
    ),
    "schedule_rules": _pay(publish_at=(NOW + timedelta(minutes=5)).isoformat()),
    "approval_hash_recorded": _upload_approval(SHA_B),
    "approval_hash_current": _upload_approval(SHA_B),
    "has_video_id": _pay(youtube_video_id=None),
    "all_segments_done": _set(segments_total=3, segments_done=1),
    "render_attempts_left": _set(attempt=2),
    "is_test_upload": _set(is_test=False),
    "subject_hash_matches": _pay(subject_sha256=SHA_B),
    # Reaching this guard needs FULLY mode + a rule, which the mode gate demands too: the gate refuses first.
    "auto_rule_recorded_if_auto": lambda c: (
        c.go_auto(),
        c.payload.pop("auto_rule_id"),
        setattr(c, "expect", "ACTOR_NOT_ALLOWED"),
    ),
    "auto_allowed_for_subject": lambda c: (
        c.go_auto(),
        setattr(c.entity, "subject_type", "UPLOAD_PACKAGE"),
        c.db.flush(),
    ),
    "has_comment": _pay(comment=""),
    "enough_sample_minutes": _set(sample_seconds=Decimal(10)),
    "live_consent_recorded": _pay(one_time_code=None),
    "voice_verification_passed": _pay(speaker_similarity=0.1),
    "within_budget": _pay(budget_remaining_minor=100),
    "stock_provider_enabled": _pay(provider_enabled=False),
    "licence_fits_channel": lambda c: (
        setattr(c.entity, "licence_type", "editorial-only"),
        setattr(c.w.channel, "is_monetised", True),
        c.db.flush(),
    ),
    "rights_record_written": _set(asset_id=None),
}


def _allowed_actor(edge: Edge) -> str:
    for kind in ("OWNER", "SYSTEM", "ORCH", "AGENT", "AUDITOR"):
        if kind in edge.actors:
            return kind
    raise AssertionError(edge)


def _case(w: W, machine: Machine, edge: Edge, source: str) -> Case:
    c = Case(w, make(w, machine, source), actor=_allowed_actor(edge))
    for g in edge.guards:
        GOOD[g](c)
    return c


def _run(c: Case, machine: Machine, event: str) -> engine.TransitionResult:
    return engine.transition(
        c.db, machine, c.entity.id, event, actor=c.w.actor(c.actor), payload=c.payload, now=NOW
    )


def test_fixtures_cover_every_guard() -> None:
    from tubeforge.orchestrator.guards import GUARDS

    assert set(GOOD) == set(GUARDS) == set(BAD)


@pytest.mark.parametrize("name", sorted(MACHINES))
def test_every_transition_with_and_without_its_guards(
    db: Session, env: Env, name: str, subtests: Any
) -> None:
    machine = MACHINES[name]
    w = world(db, env)
    for edge in machine.edges:
        for source in sorted(edge.source):
            with subtests.test(msg=f"{source} --{edge.event}--> {edge.target} ok"):
                sp = db.begin_nested()
                try:
                    c = _case(w, machine, edge, source)
                    res = _run(c, machine, edge.event)
                    assert (res.from_state, res.to_state, res.replayed) == (source, edge.target, False)
                    assert db.get_one(machine.model, c.entity.id).state == edge.target
                finally:
                    sp.rollback()
            for g in edge.guards:
                with subtests.test(msg=f"{source} --{edge.event}--> {edge.target} without {g}"):
                    sp = db.begin_nested()
                    try:
                        c = _case(w, machine, edge, source)
                        BAD[g](c)
                        with pytest.raises(TransitionRejected) as exc:
                            _run(c, machine, edge.event)
                        assert exc.value.code == c.expect, exc.value
                    finally:
                        sp.rollback()


@pytest.mark.parametrize("name", sorted(MACHINES))
def test_unlisted_pairs_are_rejected(db: Session, env: Env, name: str) -> None:
    machine = MACHINES[name]
    w = world(db, env)
    events = machine.events() | {"nonsense"}
    for state in machine.states:
        listed = {e.event for e in machine.edges_from(state)}
        for event in sorted(events - listed):
            if machine.universal and event in engine.UNIVERSAL_EVENTS:
                continue  # covered by the universal-state test
            sp = db.begin_nested()
            try:
                entity = make(w, machine, state)
                with pytest.raises(TransitionRejected) as exc:
                    engine.transition(db, machine, entity.id, event, actor=w.actor("OWNER"), now=NOW)
                assert exc.value.code in {"INVALID_TRANSITION", "TERMINAL_STATE"}, (state, event)
            finally:
                sp.rollback()


@pytest.mark.parametrize("name", sorted(MACHINES))
def test_emergency_stop_blocks_all_but_pause_cancel_and_safety(db: Session, env: Env, name: str) -> None:
    machine = MACHINES[name]
    w = world(db, env)
    db.get_one(SystemSettings, 1).emergency_stop = True
    db.flush()
    for edge in machine.edges:
        source = sorted(edge.source)[0]
        sp = db.begin_nested()
        try:
            c = _case(w, machine, edge, source)
            exempt = edge.target in {"PAUSED", "CANCELLED"} or edge.es_exempt
            if exempt:
                assert _run(c, machine, edge.event).to_state == edge.target
            else:
                with pytest.raises(TransitionRejected) as exc:
                    _run(c, machine, edge.event)
                assert exc.value.code == "EMERGENCY_STOP", edge
        finally:
            sp.rollback()


# ----------------------------------------------------------------------- idempotency / actors / modes
def test_same_event_twice_is_one_transition(db: Session, env: Env) -> None:
    w = world(db, env)
    idea = make(w, MACHINES["video_idea"], "SUGGESTED")
    first = engine.transition(
        db, MACHINES["video_idea"], idea.id, "shortlist", actor=w.actor("OWNER"), idempotency_key="k1"
    )
    again = engine.transition(
        db, MACHINES["video_idea"], idea.id, "shortlist", actor=w.actor("OWNER"), idempotency_key="k1"
    )
    assert not first.replayed and again.replayed and again.transition_id == first.transition_id
    count = db.scalar(
        select(func.count()).select_from(WorkflowTransition).where(WorkflowTransition.entity_id == idea.id)
    )
    assert count == 1


def test_agents_can_never_confirm_a_stock_purchase(db: Session, env: Env) -> None:
    w = world(db, env)
    stock = MACHINES["stock_purchase"]
    for actor in ("AGENT", "ORCH", "SYSTEM"):
        p = make(w, stock, "QUOTED")
        w.channel.operating_mode = "FULLY_AUTOMATIC"
        with pytest.raises(TransitionRejected) as exc:
            engine.transition(
                db,
                stock,
                p.id,
                "confirm",
                actor=w.actor(actor),
                payload={"auto_rule_id": "r", "budget_remaining_minor": 10**6, "provider_enabled": True},
            )
        assert exc.value.code == "ACTOR_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("mode", "gate", "auto_rule", "allowed"),
    [
        ("MANUAL", "", True, False),
        ("SEMI_AUTOMATIC", "", False, True),
        ("SEMI_AUTOMATIC", "S", True, False),
        ("FULLY_AUTOMATIC", "S", False, False),
        ("FULLY_AUTOMATIC", "S", True, True),
        ("FULLY_AUTOMATIC", "SF", True, False),
    ],
)
def test_mode_gates_for_the_orchestrator(
    db: Session, env: Env, mode: str, gate: str, auto_rule: bool, allowed: bool
) -> None:
    """[S]/[F] gates (rule 6): which owner gates the orchestrator may take in each mode."""
    w = world(db, env)
    w.channel.operating_mode = mode
    event, state = {
        "": ("approve_research", "RESEARCH_REVIEW"),
        "S": ("approve_script", "SCRIPT_REVIEW"),
        "SF": ("approve_publish", "READY_FOR_APPROVAL"),
    }[gate]
    edge = PROJECT.edge(state, event)
    assert edge is not None and edge.gate == gate
    c = _case(w, PROJECT, edge, state)
    c.actor = "ORCH"
    if auto_rule:
        c.payload["auto_rule_id"] = "rule-7"
    if allowed:
        assert _run(c, PROJECT, event).to_state == edge.target
        audit = db.execute(text("SELECT details FROM audit_log ORDER BY id DESC LIMIT 1")).scalar_one()
        assert audit.get("auto_rule_id") == ("rule-7" if auto_rule else None)
    else:
        with pytest.raises(TransitionRejected) as exc:
            _run(c, PROJECT, event)
        assert exc.value.code == "ACTOR_NOT_ALLOWED"


def test_universal_pause_resume_cancel_fail_retry(db: Session, env: Env) -> None:
    w = world(db, env)
    p = _project(w, "SCRIPTING")
    owner, system = w.actor("OWNER"), w.actor("SYSTEM")
    assert engine.transition(db, PROJECT, p.id, "pause", actor=system).to_state == "PAUSED"
    assert db.get_one(VideoProject, p.id).resume_to_state == "SCRIPTING"
    with pytest.raises(TransitionRejected):  # the system resumes only after quota/resource waits
        engine.transition(db, PROJECT, p.id, "resume", actor=system)
    assert (
        engine.transition(db, PROJECT, p.id, "resume", actor=system, payload={"reason": "quota"}).to_state
        == "SCRIPTING"
    )
    engine.transition(db, PROJECT, p.id, "fail", actor=w.actor("AGENT"))
    with pytest.raises(TransitionRejected):
        engine.transition(db, PROJECT, p.id, "retry", actor=system)
    assert engine.transition(db, PROJECT, p.id, "retry", actor=owner).to_state == "SCRIPTING"
    with pytest.raises(TransitionRejected):
        engine.transition(db, PROJECT, p.id, "cancel", actor=system)
    assert engine.transition(db, PROJECT, p.id, "cancel", actor=owner).to_state == "CANCELLED"
    with pytest.raises(TransitionRejected) as exc:
        engine.transition(db, PROJECT, p.id, "resume", actor=owner)
    assert exc.value.code == "TERMINAL_STATE"


def test_failed_project_notifies_the_owner(db: Session, env: Env) -> None:
    w = world(db, env)
    p = _project(w, "RENDERING")
    engine.transition(db, PROJECT, p.id, "fail", actor=w.actor("SYSTEM"))
    note = db.scalars(select(Notification).where(Notification.entity_id == p.id)).one()
    assert note.event_type == "project.failed"


# ------------------------------------------------------------------------------------------ approvals
def test_approvals_are_bound_to_the_content_hash(db: Session, env: Env) -> None:
    w = world(db, env)
    owner = w.actor("OWNER")
    p = _project(w, "APPROVED")
    req = approvals.request(
        db,
        subject_type="UPLOAD_PACKAGE",
        subject_id=p.id,
        subject_sha256=SHA_A,
        channel_id=w.channel.id,
        actor=w.actor("ORCH"),
    )
    assert (
        approvals.request(
            db,
            subject_type="UPLOAD_PACKAGE",
            subject_id=p.id,
            subject_sha256=SHA_A,
            channel_id=w.channel.id,
            actor=w.actor("ORCH"),
        ).id
        == req.id
    )
    with pytest.raises(approvals.ApprovalStale):  # decided against other content
        approvals.decide(db, req.id, "APPROVE", actor=owner, actor_user_id=env.owner.id, subject_sha256=SHA_B)
    assert db.get_one(ApprovalRequest, req.id).state == "EXPIRED"

    req = approvals.request(
        db,
        subject_type="UPLOAD_PACKAGE",
        subject_id=p.id,
        subject_sha256=SHA_A,
        channel_id=w.channel.id,
        actor=w.actor("ORCH"),
    )
    done = approvals.decide(
        db, req.id, "APPROVE", actor=owner, actor_user_id=env.owner.id, subject_sha256=SHA_A
    )
    assert done.state == "APPROVED" and done.decided_by == env.owner.id

    pay = {"approval_request_id": str(req.id), "current_package_sha256": SHA_A}
    sp = db.begin_nested()
    assert (
        engine.transition(db, PROJECT, p.id, "start_upload", actor=w.actor("ORCH"), payload=pay).to_state
        == "UPLOADING"
    )
    sp.rollback()
    # Editing the metadata after approval changes the package hash: the approval is invalidated…
    assert (
        approvals.invalidate_subject(db, subject_type="UPLOAD_PACKAGE", subject_id=p.id, new_sha256=SHA_B)
        == 1
    )
    assert db.get_one(ApprovalRequest, req.id).state == "INVALIDATED"
    # …and APPROVED → UPLOADING is refused (WORKFLOW_STATE_MACHINE §10).
    with pytest.raises(TransitionRejected) as exc:
        engine.transition(
            db,
            PROJECT,
            p.id,
            "start_upload",
            actor=w.actor("ORCH"),
            payload={**pay, "current_package_sha256": SHA_B},
        )
    assert exc.value.code == "GUARD_FAILED"


def test_owner_only_subjects_and_expiry(db: Session, env: Env) -> None:
    w = world(db, env)
    w.channel.operating_mode = "FULLY_AUTOMATIC"
    req = approvals.request(
        db,
        subject_type="SCRIPT",
        subject_id=uuid7(),
        subject_sha256=SHA_A,
        channel_id=w.channel.id,
        actor=w.actor("ORCH"),
        now=NOW,
    )
    auto = approvals.decide(
        db,
        req.id,
        "APPROVE",
        actor=w.actor("ORCH"),
        actor_user_id=None,
        subject_sha256=SHA_A,
        auto_rule_id="r1",
    )
    assert auto.state == "APPROVED" and auto.auto_rule_id == "r1"
    money = approvals.request(
        db,
        subject_type="STOCK_PURCHASE",
        subject_id=uuid7(),
        subject_sha256=SHA_A,
        channel_id=w.channel.id,
        actor=w.actor("ORCH"),
        now=NOW,
    )
    with pytest.raises(TransitionRejected):
        approvals.decide(
            db,
            money.id,
            "APPROVE",
            actor=w.actor("ORCH"),
            actor_user_id=None,
            subject_sha256=SHA_A,
            auto_rule_id="r1",
        )
    assert approvals.expire_due(db, now=NOW + timedelta(days=15)) == 1
    assert db.get_one(ApprovalRequest, money.id).state == "EXPIRED"


# ------------------------------------------------------------------------------------------ reconciler
def _upload_job(w: W, state: str = "TRANSFERRING") -> UploadJob:
    job: UploadJob = make(w, MACHINES["upload_job"], state)
    return job


def _jobs_for(db: Session, job_id: uuid.UUID) -> list[tuple[int, str]]:
    return [
        (int(r[0]), str(r[1]))
        for r in db.execute(
            text("SELECT id, status FROM procrastinate_jobs WHERE args->>'upload_job_id' = :i ORDER BY id"),
            {"i": str(job_id)},
        )
    ]


def test_reconciler_requeues_a_lost_job_exactly_once(db: Session, env: Env) -> None:
    w = world(db, env)
    job = _upload_job(w)
    first = reconciler.reconcile(db, now=NOW)
    again = reconciler.reconcile(db, now=NOW)
    assert first.enqueued == [str(job.id)] and again.enqueued == []
    assert [s for _, s in _jobs_for(db, job.id)] == ["todo"]
    done = _upload_job(w, "COMPLETED")
    assert reconciler.reconcile(db, now=NOW).enqueued == [] and _jobs_for(db, done.id) == []


def test_reconciler_hands_back_a_job_whose_worker_died(db: Session, env: Env) -> None:
    """Crash simulation: the worker dies mid-job (status 'doing', no heartbeat) → re-run once."""
    w = world(db, env)
    job = _upload_job(w)
    jid = defer_in_transaction(
        db,
        "yt.upload",
        queue="youtube",
        args={"upload_job_id": str(job.id)},
        lock=f"upload-channel:{w.channel.id}",
    )
    dead = db.execute(
        text("INSERT INTO procrastinate_workers (last_heartbeat) VALUES (:t) RETURNING id"),
        {"t": NOW - timedelta(hours=1)},
    ).scalar_one()
    db.execute(
        text("UPDATE procrastinate_jobs SET status = 'doing', worker_id = :w WHERE id = :j"),
        {"w": dead, "j": jid},
    )
    res = reconciler.reconcile(db, now=NOW)
    assert res.retried_stalled == [jid] and res.enqueued == []
    assert _jobs_for(db, job.id) == [(jid, "todo")]  # the same job, waiting again, lock kept
    assert reconciler.reconcile(db, now=NOW).retried_stalled == []


def test_reconciler_waits_during_emergency_stop(db: Session, env: Env) -> None:
    w = world(db, env)
    job = _upload_job(w)
    db.get_one(SystemSettings, 1).emergency_stop = True
    db.flush()
    assert reconciler.reconcile(db, now=NOW).skipped_emergency_stop
    assert _jobs_for(db, job.id) == []


# ------------------------------------------------------------------------------------- property tests
@settings(max_examples=60, deadline=None, suppress_health_check=list(HealthCheck))
@given(
    events=st.lists(
        st.sampled_from(sorted(MACHINES["video_idea"].events() | {"pause", "bogus"})), max_size=12
    )
)
def test_property_idea_never_reaches_an_invalid_state(env: Env, events: list[str]) -> None:
    eng = create_engine(env.db_url)
    with Session(eng) as db:
        w = world(db, env)
        machine = MACHINES["video_idea"]
        idea = make(w, machine, "SUGGESTED")
        idea.calendar_date = date(2026, 1, 1)
        db.flush()
        for ev in events:
            before = db.get_one(VideoIdea, idea.id).state
            try:
                res = engine.transition(db, machine, idea.id, ev, actor=w.actor("OWNER"), now=NOW)
            except TransitionRejected:
                assert db.get_one(VideoIdea, idea.id).state == before
                continue
            edge = machine.edge(before, ev)
            assert edge is not None and res.to_state == edge.target
            assert res.to_state in machine.states
        db.rollback()
    eng.dispose()


def test_property_machine_tables_are_well_formed() -> None:
    for machine in MACHINES.values():
        for state in machine.terminal:
            assert machine.edges_from(state) == [], (machine.entity_type, state)
        reachable = {e.target for e in machine.edges} | {e for edge in machine.edges for e in edge.source}
        assert reachable <= set(machine.states)
        for edge in machine.edges:
            assert edge.actors, edge
