"""Guard registry (WORKFLOW_STATE_MACHINE guard tables).

A guard returns ``None`` when it holds, or a short owner-readable reason when it does not.
Guards read the database where the data exists today. Where the data is produced by a later
phase (research briefs, QC reports, audits), the guard reads documented *facts* from the event
payload (``FACTS`` below); that phase replaces the payload fact with a database lookup.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tubeforge.db.models import (
    ApprovalRequest,
    AssetRights,
    Channel,
    ChannelPublishingRules,
    KillSwitch,
    MediaAsset,
    OAuthConnection,
    SystemSettings,
    VoiceProfile,
    WorkflowTransition,
)
from tubeforge.orchestrator.machines import ORCH, Edge, Machine


@dataclass
class GuardContext:
    db: Session
    machine: Machine
    entity: Any
    edge: Edge
    actor_type: str  # OWNER | ORCH | AGENT | AUDITOR | SYSTEM
    payload: dict[str, Any]
    channel: Channel | None
    now: datetime

    def settings(self) -> SystemSettings:
        return self.db.get_one(SystemSettings, 1)

    def option(self, key: str, default: Any) -> Any:
        return (self.settings().settings or {}).get(key, default)

    def rules(self) -> ChannelPublishingRules | None:
        return self.db.get(ChannelPublishingRules, self.channel.id) if self.channel else None


Guard = Callable[[GuardContext], str | None]
GUARDS: dict[str, Guard] = {}
# Payload facts read by guards until their phase stores the data (name -> what it means).
FACTS: dict[str, str] = {}


def guard(name: str, *facts: str) -> Callable[[Guard], Guard]:
    def register(fn: Guard) -> Guard:
        assert name not in GUARDS, name
        GUARDS[name] = fn
        for fact in facts:
            FACTS.setdefault(fact, name)
        return fn

    return register


def _p(ctx: GuardContext, key: str, default: Any = None) -> Any:
    return ctx.payload.get(key, default)


def _override(ctx: GuardContext) -> bool:
    reason = _p(ctx, "override_reason") or ""
    return ctx.actor_type == "OWNER" and len(str(reason).strip()) >= 20


# ---------------------------------------------------------------------------------------- channel
@guard("channel_ready_to_activate")
def _channel_ready(ctx: GuardContext) -> str | None:
    ch = ctx.entity
    if ch.successful_private_test_uploads < 1:
        return "No successful private test upload yet."
    if not ch.privacy_policy_url:
        return "The privacy-policy address is missing."
    return None


@guard("oauth_healthy")
def _oauth_healthy(ctx: GuardContext) -> str | None:
    ok = ctx.db.scalar(
        select(OAuthConnection.id).where(
            OAuthConnection.channel_id == ctx.entity.id,
            OAuthConnection.status == "ACTIVE",
            OAuthConnection.revoked_at.is_(None),
        )
    )
    return None if ok else "The YouTube connection needs to be renewed."


@guard("channel_active")
def _channel_active(ctx: GuardContext) -> str | None:
    """ACTIVE — or CONNECTED for a private test project (mirrors SafeYouTubeClient I-3)."""
    state = ctx.channel.state if ctx.channel else None
    if state == "ACTIVE" or (state == "CONNECTED" and getattr(ctx.entity, "is_test", False)):
        return None
    return "The channel is not active."


@guard("publishing_switch_off", "privacy_status", "publish_at")
def _publishing_switch(ctx: GuardContext) -> str | None:
    publishing = _p(ctx, "privacy_status") in ("public", "unlisted") or bool(_p(ctx, "publish_at"))
    if not publishing:
        return None
    if ctx.settings().publishing_kill_switch:
        return "The publishing kill switch is on."
    target = str(ctx.channel.id) if ctx.channel else ""
    on = ctx.db.scalar(
        select(KillSwitch.id).where(
            KillSwitch.active.is_(True),
            KillSwitch.scope == "PUBLISHING_CHANNEL",
            KillSwitch.target_id == target,
        )
    )
    return "Publishing is switched off for this channel." if on else None


# ------------------------------------------------------------------------------------------- idea
@guard("orch_discard_only_expired", "duplicate_of")
def _orch_discard(ctx: GuardContext) -> str | None:
    if ctx.actor_type != ORCH:
        return None
    expires = ctx.entity.expires_at
    if (expires is not None and expires <= ctx.now) or _p(ctx, "duplicate_of"):
        return None
    return "The orchestrator only discards expired trend ideas or duplicates."


@guard("has_calendar_date")
def _has_date(ctx: GuardContext) -> str | None:
    return None if ctx.entity.calendar_date else "Pick a calendar date first."


@guard("idea_original", "override_reason")
def _idea_original(ctx: GuardContext) -> str | None:
    threshold = float(ctx.option("idea_similarity_threshold", 0.85))
    sim = ctx.entity.similarity_max
    if sim is None or float(sim) < threshold or _override(ctx):
        return None
    return f"Too similar to an existing idea ({float(sim):.2f} ≥ {threshold:.2f}); give a reason to override."


@guard("topic_allowed")
def _topic_allowed(ctx: GuardContext) -> str | None:
    rules = ctx.rules()
    text = " ".join(filter(None, [ctx.entity.title, ctx.entity.angle, ctx.entity.pillar])).lower()
    for topic in rules.blocked_topics if rules else []:
        if topic and re.search(rf"\b{re.escape(topic.lower())}\b", text):
            return f"The topic “{topic}” is blocked for this channel."
    return None


@guard("calendar_date_reached_if_auto")
def _date_reached(ctx: GuardContext) -> str | None:
    if ctx.actor_type != ORCH:
        return None
    tz = ZoneInfo(ctx.settings().owner_timezone)
    day = ctx.entity.calendar_date
    return (
        None
        if day is not None and day <= ctx.now.astimezone(tz).date()
        else "The calendar date is not reached."
    )


# ---------------------------------------------------------------------------------------- project
def _flags(*keys: str) -> Guard:
    def check(ctx: GuardContext) -> str | None:
        missing = [k for k in keys if not _p(ctx, k)]
        return f"Not done yet: {', '.join(missing)}." if missing else None

    return check


GUARDS["research_and_fact_check_done"] = _flags("research_done", "fact_check_done")
GUARDS["script_and_fact_check_done"] = _flags("script_done", "fact_check_done")
GUARDS["script_locked"] = _flags("script_version_locked")
GUARDS["narration_complete"] = lambda ctx: (
    None if _p(ctx, "scenes_without_narration", 1) == 0 else "Some scenes have no narration."
)
GUARDS["timeline_and_proxy_ready"] = _flags("timeline_version_id", "proxy_ready")
GUARDS["has_video_id"] = lambda ctx: (
    None
    if _p(ctx, "youtube_video_id") or getattr(ctx.entity, "youtube_video_id", None)
    else "No video ID yet."
)
for _fact in (
    "research_done",
    "fact_check_done",
    "script_done",
    "script_version_locked",
    "scenes_without_narration",
    "timeline_version_id",
    "proxy_ready",
    "youtube_video_id",
):
    FACTS.setdefault(_fact, "flags")


@guard("research_brief_valid", "claims")
def _research_valid(ctx: GuardContext) -> str | None:
    claims = _p(ctx, "claims")
    if not isinstance(claims, list) or not claims:
        return "The research brief has no claims."
    if any(int(c.get("sources", 0)) < 1 for c in claims):
        return "Every claim needs at least one source."
    if any(c.get("verdict") == "contradicted" for c in claims) and not _override(ctx):
        return "A claim is contradicted by its sources; fix it or give a reason to override."
    return None


@guard("no_contradicted_claims", "contradicted_claims")
def _no_contradicted(ctx: GuardContext) -> str | None:
    n = int(_p(ctx, "contradicted_claims", 1))
    return None if n == 0 or _override(ctx) else f"{n} contradicted claim(s) in the script."


@guard("owner_value_add", "value_add_fields")
def _value_add(ctx: GuardContext) -> str | None:
    need = int(ctx.option("min_value_add_fields", 1))
    have = int(_p(ctx, "value_add_fields", 0))
    return None if have >= need else f"Add your own value: {have} of {need} owner fields filled."


@guard("duration_fits_format", "estimated_duration_s")
def _duration(ctx: GuardContext) -> str | None:
    secs = _p(ctx, "estimated_duration_s")
    if secs is None:
        return "The estimated duration is missing."
    if ctx.entity.format == "SHORT" and float(secs) > 180:
        return "A Short must be 3 minutes or less."
    return None


@guard("scenes_have_rights_cleared_visuals", "scenes_without_visual", "unconfirmed_stock_purchases")
def _rights(ctx: GuardContext) -> str | None:
    if int(_p(ctx, "scenes_without_visual", 1)) != 0:
        return "Some scenes have no visual."
    if int(_p(ctx, "unconfirmed_stock_purchases", 0)) != 0:
        return "A stock purchase is waiting for your confirmation."
    rows = ctx.db.execute(
        select(
            MediaAsset.id,
            AssetRights.asset_id,
            AssetRights.editorial_only,
            AssetRights.commercial_use_allowed,
        )
        .outerjoin(AssetRights, AssetRights.asset_id == MediaAsset.id)
        .where(
            MediaAsset.project_id == ctx.entity.id,
            MediaAsset.kind.in_(("IMAGE", "VIDEO_CLIP")),
            MediaAsset.deleted_at.is_(None),
        )
    ).all()
    if any(r[1] is None for r in rows):
        return "An asset has no rights record."
    monetised = bool(ctx.channel and ctx.channel.is_monetised)
    if monetised and any(r[2] or not r[3] for r in rows):
        return "An editorial-only or non-commercial asset cannot be used on a monetised channel."
    return None


@guard("voice_consent_valid", "voice_source", "voice_profile_id", "tts_licence_commercial")
def _voice_consent(ctx: GuardContext) -> str | None:
    source = _p(ctx, "voice_source")
    if source == "owner_clone":
        vid = _p(ctx, "voice_profile_id")
        profile = ctx.db.get(VoiceProfile, uuid.UUID(str(vid))) if vid else None
        if profile is None or profile.state != "READY":
            return "The cloned voice has no valid consent record."
    if source == "tts" and not _p(ctx, "tts_licence_commercial"):
        return "The TTS voice's licence does not allow commercial use."
    return None


def _approval(ctx: GuardContext, subject_type: str, sha: str | None) -> ApprovalRequest | None:
    return ctx.db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.subject_type == subject_type,
            ApprovalRequest.subject_id == ctx.entity.id,
            ApprovalRequest.state == "APPROVED",
            ApprovalRequest.subject_sha256 == (sha or ""),
        )
    )


@guard("cut_version_approved", "timeline_sha256")
def _cut_approved(ctx: GuardContext) -> str | None:
    ok = _approval(ctx, "ROUGH_CUT", _p(ctx, "timeline_sha256"))
    return None if ok else "This exact cut has not been approved."


@guard("external_editor_enabled")
def _editor(ctx: GuardContext) -> str | None:
    return None if ctx.option("external_editors", []) else "No external editor is enabled in Settings."


@guard("reimport_declared", "declaration")
def _declared(ctx: GuardContext) -> str | None:
    d = _p(ctx, "declaration") or {}
    missing = [k for k in ("app", "plan", "assets", "ai_content") if k not in d]
    return f"Complete the declaration: {', '.join(missing)}." if missing else None


@guard("qc_passed", "qc")
def _qc(ctx: GuardContext) -> str | None:
    qc = _p(ctx, "qc") or {}
    checks = [
        (abs(float(qc.get("duration_delta_s", 99))) <= 0.1, "duration"),
        (bool(qc.get("streams_ok")), "streams"),
        (bool(qc.get("resolution_ok")), "resolution/fps"),
        (abs(float(qc.get("loudness_delta_lu", 99))) <= 1.0, "loudness"),
        (float(qc.get("black_or_frozen_s", 99)) <= 2.0, "black/frozen picture"),
        (float(qc.get("silence_gap_s", 99)) <= 3.0, "silence"),
    ]
    failed = [name for ok, name in checks if not ok]
    return f"Quality check failed: {', '.join(failed)}." if failed else None


@guard("qc_loops_left")
def _qc_loops(ctx: GuardContext) -> str | None:
    loops = ctx.db.scalar(
        select(func.count())
        .select_from(WorkflowTransition)
        .where(
            WorkflowTransition.entity_id == ctx.entity.id,
            WorkflowTransition.from_state == "RENDERING",
            WorkflowTransition.to_state == "ASSEMBLY",
        )
    )
    return None if int(loops or 0) < 2 else "Two automatic fixes already failed."


@guard(
    "package_complete", "thumbnails_passing", "title", "chapters_valid", "captions_synced", "synthetic_reason"
)
def _package(ctx: GuardContext) -> str | None:
    problems = []
    if int(_p(ctx, "thumbnails_passing", 0)) < 3:
        problems.append("3 thumbnails")
    title = str(_p(ctx, "title") or "")
    if not title or len(title) > 100:
        problems.append("a title of at most 100 characters")
    if not _p(ctx, "chapters_valid"):
        problems.append("valid chapters")
    if not _p(ctx, "captions_synced"):
        problems.append("synced captions")
    if _p(ctx, "contains_synthetic_media") is None or not _p(ctx, "synthetic_reason"):
        problems.append("the AI-disclosure decision with a reason")
    return f"The package needs {', '.join(problems)}." if problems else None


def _audits(ctx: GuardContext) -> list[dict[str, Any]]:
    audits = _p(ctx, "audits")
    return audits if isinstance(audits, list) else []


@guard("critical_audit_failure", "audits")
def _critical(ctx: GuardContext) -> str | None:
    bad = [a for a in _audits(ctx) if a.get("status") == "FAILED" and a.get("critical")]
    return None if bad else "There is no critical audit failure."


@guard("audits_pass_thresholds", "originality_score", "caps_ok")
def _audits_pass(ctx: GuardContext) -> str | None:
    audits = _audits(ctx)
    needed = {"CONTENT", "COPYRIGHT", "POLICY", "QUALITY", "THUMBNAIL"}
    present = {str(a.get("kind")) for a in audits}
    if not needed <= present:
        return f"Audits missing: {', '.join(sorted(needed - present))}."
    if any(a.get("status") != "PASSED" for a in audits):
        return "Not every audit passed."
    rules = ctx.rules()
    minimum = float(rules.min_originality_score) if rules else 70.0
    if float(_p(ctx, "originality_score", 0)) < minimum:
        return f"Originality is below {minimum:g}."
    if not _p(ctx, "caps_ok"):
        return "The channel's publishing caps would be exceeded."
    return None


@guard("override_reason")
def _override_reason(ctx: GuardContext) -> str | None:
    return None if _override(ctx) else "An override needs a written reason of at least 20 characters."


@guard("no_copyright_critical")
def _no_copyright(ctx: GuardContext) -> str | None:
    bad = [
        a
        for a in _audits(ctx)
        if a.get("kind") == "COPYRIGHT" and a.get("status") == "FAILED" and a.get("critical")
    ]
    return "Copyright-critical failures cannot be overridden; they must be fixed." if bad else None


@guard("publish_choices_explicit", "made_for_kids", "contains_synthetic_media", "thumbnail_id")
def _choices(ctx: GuardContext) -> str | None:
    missing = []
    if _p(ctx, "privacy_status") not in ("private", "unlisted", "public"):
        missing.append("privacy")
    if not isinstance(_p(ctx, "made_for_kids"), bool):
        missing.append("made for kids")
    if not isinstance(_p(ctx, "contains_synthetic_media"), bool):
        missing.append("AI disclosure")
    if not _p(ctx, "thumbnail_id"):
        missing.append("thumbnail")
    if not _p(ctx, "title"):
        missing.append("title")
    return f"Choose explicitly: {', '.join(missing)}." if missing else None


@guard("private_only_respected")
def _private_only(ctx: GuardContext) -> str | None:
    if (
        ctx.channel
        and ctx.channel.private_only_mode
        and (_p(ctx, "privacy_status") != "private" or _p(ctx, "publish_at"))
    ):
        return "Private-only mode is on: the video must be private and not scheduled."
    return None


@guard("schedule_rules")
def _schedule(ctx: GuardContext) -> str | None:
    at = _p(ctx, "publish_at")
    if not at:
        return None
    when = at if isinstance(at, datetime) else datetime.fromisoformat(str(at))
    if _p(ctx, "privacy_status") != "private":
        return "A scheduled video must be private until its publish time."
    if when < ctx.now + timedelta(minutes=15):
        return "The publish time must be at least 15 minutes ahead."
    return None


def _upload_approval(ctx: GuardContext) -> ApprovalRequest | None:
    aid = _p(ctx, "approval_request_id")
    row = ctx.db.get(ApprovalRequest, uuid.UUID(str(aid))) if aid else None
    if row is None or row.subject_type != "UPLOAD_PACKAGE" or row.subject_id != ctx.entity.id:
        return None
    return row


@guard("approval_hash_recorded", "approval_request_id", "package_sha256")
def _approval_recorded(ctx: GuardContext) -> str | None:
    row = _upload_approval(ctx)
    if row is None or row.state != "APPROVED" or row.subject_sha256 != _p(ctx, "package_sha256"):
        return "The approval of this exact package is not recorded."
    return None


@guard("approval_hash_current", "current_package_sha256")
def _approval_current(ctx: GuardContext) -> str | None:
    row = _upload_approval(ctx)
    if row is None or row.state != "APPROVED":
        return "The approval is missing or no longer valid."
    if row.subject_sha256 != _p(ctx, "current_package_sha256"):
        return "The package changed after approval; approve it again."
    return None


# ----------------------------------------------------------------------------------------- render
@guard("all_segments_done")
def _segments(ctx: GuardContext) -> str | None:
    job = ctx.entity
    return None if job.segments_done >= job.segments_total else "Segments are still rendering."


@guard("render_attempts_left")
def _attempts(ctx: GuardContext) -> str | None:
    return None if ctx.entity.attempt < 2 else "The render failed twice."


# ----------------------------------------------------------------------------------------- upload
@guard("is_test_upload")
def _is_test(ctx: GuardContext) -> str | None:
    return (
        None if ctx.entity.is_test else "Real uploads go through the thumbnail, caption and playlist steps."
    )


# --------------------------------------------------------------------------------------- approval
@guard("subject_hash_matches", "subject_sha256")
def _subject_hash(ctx: GuardContext) -> str | None:
    return None if _p(ctx, "subject_sha256") == ctx.entity.subject_sha256 else "APPROVAL_STALE"


@guard("auto_rule_recorded_if_auto", "auto_rule_id")
def _auto_rule(ctx: GuardContext) -> str | None:
    if ctx.actor_type != ORCH:
        return None
    return None if _p(ctx, "auto_rule_id") else "An automatic approval must name its rule."


# Decisions only the owner can make, whatever the operating mode (money, privacy, permissions).
OWNER_ONLY_SUBJECTS = frozenset(
    {
        "UPLOAD_PACKAGE",
        "AUTO_RULES",
        "STOCK_PURCHASE",
        "PRIVATE_ONLY_OFF",
        "MODE_CHANGE",
        "PAID_PROVIDER_ENABLE",
    }
)


@guard("auto_allowed_for_subject")
def _auto_subject(ctx: GuardContext) -> str | None:
    if ctx.actor_type == ORCH and ctx.entity.subject_type in OWNER_ONLY_SUBJECTS:
        return "Only the owner can approve this."
    return None


@guard("has_comment", "comment")
def _comment(ctx: GuardContext) -> str | None:
    return None if str(_p(ctx, "comment") or "").strip() else "Say what should change."


# ------------------------------------------------------------------------------------------ voice
@guard("enough_sample_minutes")
def _samples(ctx: GuardContext) -> str | None:
    need = float(ctx.option("voice_min_sample_seconds", 180))
    return None if float(ctx.entity.sample_seconds) >= need else f"Record at least {need / 60:g} minutes."


@guard("live_consent_recorded", "consent_audio_asset_id", "one_time_code")
def _consent(ctx: GuardContext) -> str | None:
    ok = _p(ctx, "consent_audio_asset_id") and _p(ctx, "one_time_code")
    return None if ok else "Read the consent text and the one-time code aloud (live microphone)."


@guard("voice_verification_passed", "stt_code_match", "speaker_similarity")
def _verified(ctx: GuardContext) -> str | None:
    threshold = float(ctx.option("voice_similarity_threshold", 0.75))
    if not _p(ctx, "stt_code_match"):
        return "The spoken code did not match."
    if float(_p(ctx, "speaker_similarity", 0)) < threshold:
        return "The consent recording does not match the voice samples."
    return None


# ------------------------------------------------------------------------------------------ stock
@guard("within_budget", "budget_remaining_minor")
def _budget(ctx: GuardContext) -> str | None:
    left = _p(ctx, "budget_remaining_minor")
    if left is None or int(left) < int(ctx.entity.price_minor):
        return "This purchase is over the stock budget."
    return None


@guard("stock_provider_enabled", "provider_enabled")
def _provider(ctx: GuardContext) -> str | None:
    return None if _p(ctx, "provider_enabled") else "This stock provider is not enabled."


@guard("licence_fits_channel")
def _licence(ctx: GuardContext) -> str | None:
    if ctx.channel and ctx.channel.is_monetised and "editorial" in ctx.entity.licence_type.lower():
        return "An editorial-only licence cannot be used on a monetised channel."
    return None


@guard("rights_record_written")
def _rights_written(ctx: GuardContext) -> str | None:
    asset = ctx.entity.asset_id
    ok = asset is not None and ctx.db.get(AssetRights, asset) is not None
    return None if ok else "The licence proof is not recorded yet."
