"""The workflow state machines of WORKFLOW_STATE_MACHINE.md as code tables.

Each edge names who may take it (actor types), the guards that must all hold, and whether it is an
owner-approval gate:

- ``gate=None``  — not an approval gate; only the listed actors may take it.
- ``gate=""``    — owner gate in MANUAL mode; in SEMI/FULLY modes the orchestrator may take it.
- ``gate="S"``   — stays an owner gate in SEMI mode; FULLY mode needs an auto-approval rule.
- ``gate="SF"``  — always an owner gate (e.g. the final publish approval).

``es_exempt`` marks edges that Emergency Stop must not block: moves to PAUSED / CANCELLED (rule 7)
and safety or alerting moves (token revoked, disconnect, data deletion, approval expiry,
notification delivery) — stopping those would make an emergency worse.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from tubeforge.db import models as m

OWNER, ORCH, AGENT, AUDITOR, SYSTEM = "OWNER", "ORCH", "AGENT", "AUDITOR", "SYSTEM"


def _set(*items: str) -> frozenset[str]:
    return frozenset(items)


@dataclass(frozen=True)
class Edge:
    source: frozenset[str]
    target: str
    event: str
    actors: frozenset[str]
    guards: tuple[str, ...] = ()
    gate: str | None = None
    es_exempt: bool = False


@dataclass(frozen=True)
class Machine:
    entity_type: str
    model: type[Any]
    states: tuple[str, ...]
    terminal: frozenset[str]
    edges: tuple[Edge, ...]
    universal: bool = False  # PAUSED / CANCELLED / FAILED from any non-terminal state (rule 5)
    channel_attr: str | None = "channel_id"
    _index: dict[tuple[str, str], Edge] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        for e in self.edges:
            assert e.target in self.states, (self.entity_type, e)
            for s in e.source:
                assert s in self.states, (self.entity_type, e)
                key = (s, e.event)
                assert key not in self._index, f"{self.entity_type}: two edges for {key}"
                self._index[key] = e

    def edge(self, state: str, event: str) -> Edge | None:
        return self._index.get((state, event))

    def edges_from(self, state: str) -> list[Edge]:
        return [e for e in self.edges if state in e.source]

    def events(self) -> set[str]:
        return {e.event for e in self.edges} | (
            {"pause", "resume", "cancel", "fail", "retry"} if self.universal else set()
        )


def E(  # noqa: N802 - table helper
    source: str | Iterable[str],
    target: str,
    event: str,
    actors: Iterable[str],
    guards: Iterable[str] = (),
    *,
    gate: str | None = None,
    es_exempt: bool = False,
) -> Edge:
    src = frozenset([source] if isinstance(source, str) else source)
    return Edge(src, target, event, frozenset(actors), tuple(guards), gate, es_exempt)


# ------------------------------------------------------------------------------------- 1 Channel
CHANNEL = Machine(
    "channel",
    m.Channel,
    (
        "PROPOSED",
        "APPROVED",
        "REJECTED",
        "ONBOARDING",
        "CONNECTED",
        "ACTIVE",
        "PAUSED",
        "NEEDS_REAUTH",
        "DISCONNECTING",
        "DISCONNECTED",
    ),
    terminal=_set("REJECTED"),
    channel_attr="id",
    edges=(
        E("PROPOSED", "APPROVED", "approve", [OWNER]),
        E("PROPOSED", "REJECTED", "reject", [OWNER]),
        E("APPROVED", "ONBOARDING", "start_onboarding", [OWNER]),
        E("ONBOARDING", "CONNECTED", "identity_confirmed", [OWNER]),
        E("CONNECTED", "ACTIVE", "activated", [OWNER, SYSTEM], ["channel_ready_to_activate"]),
        E(["CONNECTED", "ACTIVE"], "PAUSED", "pause", [OWNER, SYSTEM], es_exempt=True),
        E("PAUSED", "ACTIVE", "resume", [OWNER], ["oauth_healthy"]),
        E("PAUSED", "CONNECTED", "resume_connected", [OWNER], ["oauth_healthy"]),
        E(["CONNECTED", "ACTIVE", "PAUSED"], "NEEDS_REAUTH", "token_invalid", [SYSTEM], es_exempt=True),
        E("NEEDS_REAUTH", "ACTIVE", "reauthorized", [OWNER, SYSTEM]),
        E("NEEDS_REAUTH", "CONNECTED", "reauthorized_connected", [OWNER, SYSTEM]),
        E("NEEDS_REAUTH", "PAUSED", "reauthorized_paused", [OWNER, SYSTEM]),
        E(
            ["ONBOARDING", "CONNECTED", "ACTIVE", "PAUSED", "NEEDS_REAUTH"],
            "DISCONNECTING",
            "disconnect",
            [
                OWNER,
                SYSTEM,
            ],  # SYSTEM: revocation detected at Google (data_deletion_tasks REVOCATION_DETECTED)
            es_exempt=True,
        ),
        E("DISCONNECTING", "DISCONNECTED", "data_deleted", [SYSTEM], es_exempt=True),
        E("DISCONNECTED", "ONBOARDING", "reconnect", [OWNER]),
    ),
)

# ---------------------------------------------------------------------------------------- 2 Idea
IDEA = Machine(
    "video_idea",
    m.VideoIdea,
    ("SUGGESTED", "SHORTLISTED", "SCHEDULED", "APPROVED", "IN_PRODUCTION", "PRODUCED", "DISCARDED"),
    terminal=_set("PRODUCED", "DISCARDED"),
    edges=(
        E("SUGGESTED", "SHORTLISTED", "shortlist", [OWNER]),
        E("SUGGESTED", "DISCARDED", "discard", [OWNER, ORCH], ["orch_discard_only_expired"]),
        E("SHORTLISTED", "SCHEDULED", "schedule", [OWNER], ["has_calendar_date"]),
        E("SHORTLISTED", "APPROVED", "approve", [OWNER], ["idea_original", "topic_allowed"]),
        E(
            "SCHEDULED",
            "APPROVED",
            "approve_scheduled",
            [OWNER],
            ["idea_original", "topic_allowed", "calendar_date_reached_if_auto"],
            gate="S",
        ),
        E("APPROVED", "IN_PRODUCTION", "start_production", [ORCH]),
        E("IN_PRODUCTION", "PRODUCED", "produced", [ORCH, SYSTEM]),
    ),
)

# ------------------------------------------------------------------------------- 3 Video project
P = (
    "IDEA",
    "RESEARCHING",
    "RESEARCH_REVIEW",
    "SCRIPTING",
    "SCRIPT_REVIEW",
    "STORYBOARDING",
    "ASSET_GENERATION",
    "VOICEOVER",
    "ASSEMBLY",
    "ROUGH_CUT_REVIEW",
    "EXTERNAL_EDITING",
    "RENDERING",
    "PACKAGING",
    "QC_AUDIT",
    "BLOCKED",
    "READY_FOR_APPROVAL",
    "APPROVED",
    "UPLOADING",
    "PROCESSING",
    "SCHEDULED",
    "PRIVATE_DONE",
    "PUBLISHED",
    "ANALYZING",
    "ARCHIVED",
    "PAUSED",
    "CANCELLED",
    "FAILED",
)
PROJECT = Machine(
    "video_project",
    m.VideoProject,
    P,
    terminal=_set("ARCHIVED", "CANCELLED"),
    universal=True,
    edges=(
        E("IDEA", "RESEARCHING", "start_research", [ORCH]),
        E("RESEARCHING", "RESEARCH_REVIEW", "research_done", [AGENT, ORCH], ["research_and_fact_check_done"]),
        E("RESEARCH_REVIEW", "RESEARCHING", "request_changes", [OWNER]),
        E("RESEARCH_REVIEW", "SCRIPTING", "approve_research", [OWNER], ["research_brief_valid"], gate=""),
        E("SCRIPTING", "SCRIPT_REVIEW", "script_done", [AGENT, ORCH], ["script_and_fact_check_done"]),
        E("SCRIPT_REVIEW", "SCRIPTING", "request_changes", [OWNER]),
        E(
            "SCRIPT_REVIEW",
            "STORYBOARDING",
            "approve_script",
            [OWNER],
            ["script_locked", "no_contradicted_claims", "owner_value_add", "duration_fits_format"],
            gate="S",
        ),
        E("STORYBOARDING", "ASSET_GENERATION", "storyboard_done", [AGENT, ORCH, OWNER]),
        E("ASSET_GENERATION", "VOICEOVER", "assets_ready", [ORCH], ["scenes_have_rights_cleared_visuals"]),
        E("VOICEOVER", "ASSEMBLY", "narration_ready", [ORCH], ["narration_complete", "voice_consent_valid"]),
        E("ASSEMBLY", "ROUGH_CUT_REVIEW", "cut_ready", [AGENT, ORCH], ["timeline_and_proxy_ready"]),
        E("ROUGH_CUT_REVIEW", "ASSEMBLY", "request_changes", [OWNER]),
        E("ROUGH_CUT_REVIEW", "RENDERING", "approve_cut", [OWNER], ["cut_version_approved"], gate=""),
        E(
            ["ROUGH_CUT_REVIEW", "PACKAGING"],
            "EXTERNAL_EDITING",
            "edit_externally",
            [OWNER],
            ["external_editor_enabled"],
        ),
        E("EXTERNAL_EDITING", "RENDERING", "reimport", [OWNER], ["reimport_declared"]),
        E("EXTERNAL_EDITING", "ROUGH_CUT_REVIEW", "cancel_external_edit", [OWNER]),
        E("RENDERING", "PACKAGING", "render_ok", [ORCH], ["qc_passed"]),
        E("RENDERING", "ASSEMBLY", "qc_failed_fixable", [ORCH], ["qc_loops_left"]),
        E("PACKAGING", "QC_AUDIT", "package_ready", [ORCH], ["package_complete"]),
        E("QC_AUDIT", "BLOCKED", "audit_failed", [AUDITOR, ORCH], ["critical_audit_failure"]),
        E("QC_AUDIT", "READY_FOR_APPROVAL", "audits_passed", [AUDITOR, ORCH], ["audits_pass_thresholds"]),
        E("BLOCKED", "ASSEMBLY", "fix_assembly", [OWNER]),
        E("BLOCKED", "PACKAGING", "fix_packaging", [OWNER]),
        E("BLOCKED", "SCRIPTING", "fix_script", [OWNER]),
        E("BLOCKED", "READY_FOR_APPROVAL", "override", [OWNER], ["override_reason", "no_copyright_critical"]),
        E(
            "READY_FOR_APPROVAL",
            "APPROVED",
            "approve_publish",
            [OWNER],
            [
                "publish_choices_explicit",
                "private_only_respected",
                "schedule_rules",
                "approval_hash_recorded",
            ],
            gate="SF",
        ),
        E("READY_FOR_APPROVAL", "PACKAGING", "request_changes", [OWNER]),
        E(
            "APPROVED",
            "UPLOADING",
            "start_upload",
            [ORCH],
            ["approval_hash_current", "channel_active", "publishing_switch_off"],
        ),
        E("UPLOADING", "PROCESSING", "video_id_received", [SYSTEM, ORCH], ["has_video_id"]),
        E("PROCESSING", "SCHEDULED", "processed_scheduled", [SYSTEM]),
        E("PROCESSING", "PRIVATE_DONE", "processed_private", [SYSTEM]),
        E("PROCESSING", "PUBLISHED", "processed_public", [SYSTEM]),
        E(["SCHEDULED", "PRIVATE_DONE"], "PUBLISHED", "publish_detected", [SYSTEM]),
        E("PUBLISHED", "ANALYZING", "start_analysis", [ORCH]),
        E("ANALYZING", "ARCHIVED", "archive", [ORCH]),
    ),
)

# ---------------------------------------------------------------------------------------- 4 Render
R_ACTIVE = ("QUEUED", "WAITING_RESOURCES", "RUNNING", "SEGMENT_DONE", "CONCATENATING", "QC_CHECK", "RETRYING")
RENDER = Machine(
    "render_job",
    m.RenderJob,
    (*R_ACTIVE, "SUCCEEDED", "QC_FAILED", "FAILED", "CANCELLED"),
    terminal=_set("SUCCEEDED", "QC_FAILED", "FAILED", "CANCELLED"),
    edges=(
        E("QUEUED", "WAITING_RESOURCES", "wait_resources", [SYSTEM]),
        E("WAITING_RESOURCES", "QUEUED", "resources_ok", [SYSTEM]),
        E("QUEUED", "RUNNING", "start", [SYSTEM]),
        E("RUNNING", "SEGMENT_DONE", "segment_done", [SYSTEM]),
        E("SEGMENT_DONE", "RUNNING", "next_segment", [SYSTEM]),
        E("SEGMENT_DONE", "CONCATENATING", "concatenate", [SYSTEM], ["all_segments_done"]),
        E("CONCATENATING", "QC_CHECK", "concatenated", [SYSTEM]),
        E("QC_CHECK", "SUCCEEDED", "qc_pass", [SYSTEM], ["qc_passed"]),
        E("QC_CHECK", "QC_FAILED", "qc_fail", [SYSTEM]),
        E("RUNNING", "RETRYING", "error", [SYSTEM]),
        E("RETRYING", "QUEUED", "backoff_elapsed", [SYSTEM], ["render_attempts_left"]),
        E("RETRYING", "FAILED", "give_up", [SYSTEM]),
        E(R_ACTIVE, "CANCELLED", "cancel", [OWNER, SYSTEM], es_exempt=True),
    ),
)

# ---------------------------------------------------------------------------------------- 5 Upload
UPLOAD = Machine(
    "upload_job",
    m.UploadJob,
    (
        "PREFLIGHT",
        "REJECTED",
        "WAITING_QUOTA",
        "SESSION_STARTED",
        "TRANSFERRING",
        "RESUMING",
        "UPLOADED",
        "SETTING_THUMBNAIL",
        "SETTING_CAPTIONS",
        "SETTING_PLAYLIST",
        "POLLING_PROCESSING",
        "COMPLETED",
        "PROCESSING_FAILED",
        "FAILED",
    ),
    terminal=_set("REJECTED", "COMPLETED", "PROCESSING_FAILED", "FAILED"),
    edges=(
        E("PREFLIGHT", "REJECTED", "reject", [SYSTEM, ORCH]),
        E("PREFLIGHT", "WAITING_QUOTA", "wait_quota", [SYSTEM]),
        E("WAITING_QUOTA", "PREFLIGHT", "quota_reset", [SYSTEM]),
        E("PREFLIGHT", "SESSION_STARTED", "session_started", [SYSTEM]),
        E(["SESSION_STARTED", "RESUMING"], "TRANSFERRING", "transfer", [SYSTEM]),
        E(["SESSION_STARTED", "TRANSFERRING"], "RESUMING", "resume", [SYSTEM]),
        E(["TRANSFERRING", "RESUMING"], "UPLOADED", "video_id_received", [SYSTEM]),
        E("UPLOADED", "SETTING_THUMBNAIL", "set_thumbnail", [SYSTEM]),
        E("SETTING_THUMBNAIL", "SETTING_CAPTIONS", "set_captions", [SYSTEM]),
        E("SETTING_CAPTIONS", "SETTING_PLAYLIST", "set_playlist", [SYSTEM]),
        E("SETTING_PLAYLIST", "POLLING_PROCESSING", "poll", [SYSTEM]),
        E("POLLING_PROCESSING", "COMPLETED", "processing_succeeded", [SYSTEM]),
        E("POLLING_PROCESSING", "PROCESSING_FAILED", "processing_failed", [SYSTEM]),
        # Test uploads have no thumbnail/caption/playlist steps (Phase 4 addition).
        E("UPLOADED", "COMPLETED", "test_upload_done", [SYSTEM], ["is_test_upload"]),
        E(
            ["PREFLIGHT", "SESSION_STARTED", "TRANSFERRING", "RESUMING", "WAITING_QUOTA"],
            "FAILED",
            "fail",
            [SYSTEM],
            es_exempt=True,
        ),
    ),
)

# --------------------------------------------------------------------------- 6 Notification delivery
_DELIVERY_MOVES = (
    ("CREATED", "SUPPRESSED", "suppress"),
    ("CREATED", "DEFERRED", "defer"),
    ("CREATED", "DIGEST_PENDING", "to_digest"),
    ("DEFERRED", "QUEUED", "quiet_hours_end"),
    ("DIGEST_PENDING", "QUEUED", "digest_time"),
    ("CREATED", "QUEUED", "queue"),
    ("QUEUED", "SENT", "sent"),
    ("QUEUED", "RETRYING", "retry"),
    ("RETRYING", "QUEUED", "backoff_elapsed"),
    ("RETRYING", "FAILED", "give_up"),
)
NOTIFICATION = Machine(
    "notification_delivery",
    m.NotificationDelivery,
    ("CREATED", "SUPPRESSED", "DEFERRED", "DIGEST_PENDING", "QUEUED", "SENT", "RETRYING", "FAILED", "READ"),
    terminal=_set("SUPPRESSED", "FAILED", "READ"),
    channel_attr=None,
    edges=(
        *(E(src, dst, ev, [SYSTEM, ORCH], es_exempt=True) for src, dst, ev in _DELIVERY_MOVES),
        E("SENT", "READ", "read", [OWNER, SYSTEM], es_exempt=True),
    ),
)

# -------------------------------------------------------------------------------------- 7 Approval
APPROVAL = Machine(
    "approval_request",
    m.ApprovalRequest,
    ("PENDING", "APPROVED", "CHANGES_REQUESTED", "REJECTED", "EXPIRED", "INVALIDATED"),
    terminal=_set("CHANGES_REQUESTED", "REJECTED", "EXPIRED", "INVALIDATED"),
    edges=(
        E(
            "PENDING",
            "APPROVED",
            "approve",
            [OWNER],
            ["subject_hash_matches", "auto_rule_recorded_if_auto", "auto_allowed_for_subject"],
            gate="S",
        ),
        E("PENDING", "CHANGES_REQUESTED", "request_changes", [OWNER], ["has_comment"]),
        E("PENDING", "REJECTED", "reject", [OWNER]),
        E("PENDING", "EXPIRED", "expire", [SYSTEM, ORCH], es_exempt=True),
        E("APPROVED", "INVALIDATED", "invalidate", [SYSTEM, ORCH], es_exempt=True),
    ),
)

# ---------------------------------------------------------------------------------- 8 Voice profile
VOICE = Machine(
    "voice_profile",
    m.VoiceProfile,
    ("RECORDING_SAMPLES", "CONSENT_PENDING", "VERIFYING", "READY", "DISABLED", "REJECTED", "DELETED"),
    terminal=_set("REJECTED", "DELETED"),
    channel_attr=None,
    edges=(
        E("RECORDING_SAMPLES", "CONSENT_PENDING", "samples_done", [OWNER, SYSTEM], ["enough_sample_minutes"]),
        E("CONSENT_PENDING", "VERIFYING", "consent_recorded", [OWNER], ["live_consent_recorded"]),
        E("VERIFYING", "READY", "verified", [SYSTEM], ["voice_verification_passed"]),
        E("VERIFYING", "REJECTED", "verification_failed", [SYSTEM]),
        E("READY", "DISABLED", "disable", [OWNER], es_exempt=True),
        E("DISABLED", "READY", "enable", [OWNER]),
        E(["READY", "DISABLED"], "DELETED", "delete", [OWNER], es_exempt=True),
    ),
)

# --------------------------------------------------------------------------------- 9 Stock purchase
STOCK = Machine(
    "stock_purchase",
    m.StockPurchase,
    ("QUOTED", "REFUSED", "CONFIRMED", "LICENSED", "DOWNLOADED", "FAILED"),
    terminal=_set("REFUSED", "DOWNLOADED", "FAILED"),
    edges=(
        E("QUOTED", "REFUSED", "refuse", [SYSTEM, ORCH], es_exempt=True),
        # Only the owner can confirm a purchase — never an agent, never the orchestrator (ADR-0020).
        E(
            "QUOTED",
            "CONFIRMED",
            "confirm",
            [OWNER],
            ["within_budget", "stock_provider_enabled", "licence_fits_channel"],
        ),
        E("CONFIRMED", "LICENSED", "licensed", [SYSTEM]),
        E("LICENSED", "DOWNLOADED", "downloaded", [SYSTEM], ["rights_record_written"]),
        E("CONFIRMED", "FAILED", "provider_error", [SYSTEM], es_exempt=True),
    ),
)

MACHINES: dict[str, Machine] = {
    mach.entity_type: mach
    for mach in (CHANNEL, IDEA, PROJECT, RENDER, UPLOAD, NOTIFICATION, APPROVAL, VOICE, STOCK)
}
