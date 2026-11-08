# Workflow State Machines

**Version:** 0.1 (Step 0.4, for Checkpoint C3) · **Date:** 2026-11-08
**Owner of all transitions:** Master Orchestrator (`SYSTEM_ARCHITECTURE.md` §4-C).

## 0. Rules that apply to every state machine

1. **Persisted and atomic.** A transition is one DB transaction:
   - lock the entity row (`SELECT … FOR UPDATE`)
   - check the guard
   - write the new state
   - insert a `workflow_transitions` row (entity, from, to, event, actor, reason, idempotency key, timestamp)
   - insert an `audit_log` row
   - enqueue the next job(s)
2. **Idempotent.** `(entity_id, idempotency_key)` is unique in `workflow_transitions`. Replaying an event is a no-op that returns the existing result.
3. **Resumable.** On restart the orchestrator scans for entities whose state expects a job and has no live job, and re-enqueues them (a "reconciler" periodic job, every 2 min).
4. **Actors.**
   - `OWNER` — human, via the API.
   - `ORCH` — the orchestrator's automatic rules.
   - `AGENT:<id>` — task completion.
   - `AUDITOR:<id>` — an independent audit.
   - `SYSTEM` — monitors such as token health, quota or emergency stop.
5. **Universal states** (any non-terminal state can move to them):
   - `PAUSED` — by Emergency Stop, a kill switch or the owner. It stores `resume_to` = the previous state. Resuming needs an OWNER action. A SYSTEM resume is allowed only for quota and resource waits.
   - `CANCELLED` — OWNER only. Terminal.
   - `FAILED` — SYSTEM/AGENT after retries are exhausted. OWNER may retry, which moves the entity back to the last stable state.
6. **Mode-dependent approvals.** "Owner approval" gates below apply in MANUAL mode. In SEMI-AUTOMATIC mode only the gates marked **[S]** remain. In FULLY-AUTOMATIC mode only gates marked **[F]** remain; the others are satisfied by an **auto-approval record** produced by the owner-accepted rule set, if the rule conditions hold (audit scores ≥ thresholds, topic allowed, caps not exceeded, not in quiet hours).
7. **Emergency Stop** blocks every transition except → `PAUSED` / `CANCELLED`.

---

## 1. Channel

```mermaid
stateDiagram-v2
    [*] --> PROPOSED : blueprint generated (AGENT channel_strategy)
    PROPOSED --> APPROVED : OWNER approves blueprint
    PROPOSED --> REJECTED : OWNER rejects
    APPROVED --> ONBOARDING : OWNER starts guided setup
    ONBOARDING --> CONNECTED : OAuth ok AND owner confirmed channel identity
    CONNECTED --> ACTIVE : test private upload succeeded (≥1) AND privacy policy URL set
    ACTIVE --> PAUSED : OWNER / kill switch / Emergency Stop
    PAUSED --> ACTIVE : OWNER resumes (guards re-checked)
    CONNECTED --> NEEDS_REAUTH : SYSTEM token invalid_grant / revoked
    ACTIVE --> NEEDS_REAUTH : SYSTEM token invalid_grant / revoked
    NEEDS_REAUTH --> ACTIVE : OWNER re-authorises (same channel ID verified)
    ACTIVE --> DISCONNECTING : OWNER disconnects
    NEEDS_REAUTH --> DISCONNECTING : OWNER disconnects
    DISCONNECTING --> DISCONNECTED : token revoked AND API data deleted (≤ 7 days, DP-4)
    DISCONNECTED --> ONBOARDING : OWNER reconnects
    REJECTED --> [*]
```

| Transition | Guard | Side effects |
|---|---|---|
| ONBOARDING → CONNECTED | `channels.list(mine)` ID == ID the owner confirmed. Scopes granted ⊇ required. | Store encrypted token. Set `private_only_mode = ON`. |
| CONNECTED → ACTIVE | ≥ 1 successful private test upload (`is_test`) on a test channel **or** on this channel. Privacy-policy URL configured. | Enable job scheduling for the channel. |
| any → NEEDS_REAUTH | Token refresh fails with `invalid_grant` or 401. | Pause the channel's YouTube jobs. Critical notification. |
| DISCONNECTING → DISCONNECTED | Revoke call done (or token already invalid). Retention job purged YouTube API data for the channel. | Deletion deadline monitor closed. |
| `private_only_mode` OFF | OWNER only. ≥ 3 successful private test uploads. | Audit log + security event. |

## 2. Idea

```mermaid
stateDiagram-v2
    [*] --> SUGGESTED : AGENT idea_generation / OWNER manual
    SUGGESTED --> SHORTLISTED : OWNER
    SUGGESTED --> DISCARDED : OWNER / ORCH (expired trend, duplicate)
    SHORTLISTED --> SCHEDULED : OWNER assigns calendar date
    SHORTLISTED --> APPROVED : OWNER approves (creates Video Project)
    SCHEDULED --> APPROVED : OWNER / ORCH on date [S]
    APPROVED --> IN_PRODUCTION : project created
    IN_PRODUCTION --> PRODUCED : project PUBLISHED or PRIVATE_DONE
    DISCARDED --> [*]
    PRODUCED --> [*]
```

Guards:
- **→ APPROVED:** similarity to existing channel ideas and videos < threshold (default 0.85), or OWNER override with reason. Topic not on the channel's blocked list.
- **ORCH discard:** a trend-based idea past `expires_at`, unless shortlisted.

## 3. Video Project (long-form and Short share this machine; `format` = LONG | SHORT)

```mermaid
stateDiagram-v2
    [*] --> IDEA
    IDEA --> RESEARCHING : ORCH (idea approved)
    RESEARCHING --> RESEARCH_REVIEW : AGENT research + AGENT fact_check done
    RESEARCH_REVIEW --> RESEARCHING : OWNER requests changes
    RESEARCH_REVIEW --> SCRIPTING : OWNER approves
    SCRIPTING --> SCRIPT_REVIEW : AGENT scriptwriting + AGENT fact_check done
    SCRIPT_REVIEW --> SCRIPTING : OWNER requests changes
    SCRIPT_REVIEW --> STORYBOARDING : OWNER approves [S] (value-add fields checked)
    STORYBOARDING --> ASSET_GENERATION : AGENT storyboard done (OWNER review optional)
    ASSET_GENERATION --> VOICEOVER : all scenes have rights-cleared visuals
    VOICEOVER --> ASSEMBLY : narration complete (owner rec / owner clone / TTS)
    ASSEMBLY --> ROUGH_CUT_REVIEW : timeline JSON + proxy render ready
    ROUGH_CUT_REVIEW --> ASSEMBLY : OWNER requests changes
    ROUGH_CUT_REVIEW --> RENDERING : OWNER approves cut
    RENDERING --> PACKAGING : final render + QC report OK
    RENDERING --> ASSEMBLY : QC failed (auto-fixable) – max 2 loops
    PACKAGING --> QC_AUDIT : thumbnails ≥3, SEO package, captions, AI-disclosure assessment done
    QC_AUDIT --> BLOCKED : any critical audit failure
    QC_AUDIT --> READY_FOR_APPROVAL : all audits ≥ thresholds
    BLOCKED --> ASSEMBLY : OWNER chooses fix path (or PACKAGING / SCRIPTING)
    BLOCKED --> READY_FOR_APPROVAL : OWNER override with reason (logged)
    READY_FOR_APPROVAL --> APPROVED : OWNER approves [S][F] – selects thumbnail, privacy, madeForKids, publish time
    READY_FOR_APPROVAL --> PACKAGING : OWNER requests changes
    APPROVED --> UPLOADING : ORCH creates Upload Job
    UPLOADING --> PROCESSING : video_id received
    PROCESSING --> SCHEDULED : privacy=private + publishAt set
    PROCESSING --> PRIVATE_DONE : privacy=private, no schedule (owner publishes in Studio)
    PROCESSING --> PUBLISHED : privacy=public/unlisted (approved)
    SCHEDULED --> PUBLISHED : SYSTEM detects publish time passed (videos.list status)
    PRIVATE_DONE --> PUBLISHED : SYSTEM detects owner made it public
    PUBLISHED --> ANALYZING : ORCH after 48 h
    ANALYZING --> ARCHIVED : ORCH after analysis window (default 28 days)
    ARCHIVED --> [*]
```

Universal: any non-terminal state → `PAUSED` | `CANCELLED` | `FAILED`.

### Guard table (Video Project)

| Transition | Guard (all must hold) | Responsible |
|---|---|---|
| RESEARCH_REVIEW → SCRIPTING | Research brief valid. Every claim has ≥ 1 source. No `contradicted` claim without owner override. | OWNER |
| SCRIPT_REVIEW → STORYBOARDING | Script version locked. Fact-check: 0 `contradicted` (or override). **Owner value-add** record exists (≥ 1 field filled; configurable minimum). Estimated duration fits the format (SHORT ≤ 180 s). | OWNER [S] |
| ASSET_GENERATION → VOICEOVER | Every scene has ≥ 1 visual asset with a valid **rights record**. No asset with an editorial-only or non-commercial licence on a monetised channel. Stock purchases (if any) confirmed individually by the owner within budget. | ORCH |
| VOICEOVER → ASSEMBLY | Every scene has narration audio. If `voice_source = owner_clone`, a valid consent record exists for the voice profile. TTS voices have commercial-OK licences. | ORCH |
| ROUGH_CUT_REVIEW → RENDERING | Owner approved the specific timeline version hash. | OWNER |
| RENDERING → PACKAGING | QC: duration matches the timeline (±0.1 s), required streams present, resolution and fps as configured, integrated loudness within ±1 LU of target, no black or frozen segment > 2 s (unless intended), no silence gap > 3 s (unless intended). | ORCH |
| PACKAGING → QC_AUDIT | ≥ 3 thumbnails pass technical checks. SEO: title ≤ 100 chars, chapters validated against the final duration. Captions synced. `containsSyntheticMedia` decision + reason present. | ORCH |
| QC_AUDIT → READY_FOR_APPROVAL | All audit reports PASSED (content, copyright, policy, quality, thumbnail). Originality score ≥ threshold. Channel publishing caps would not be exceeded. | AUDITORS |
| BLOCKED → READY_FOR_APPROVAL | OWNER override with a written reason (≥ 20 chars). **Not available** for copyright-critical failures (missing rights record) — those must be fixed. | OWNER |
| READY_FOR_APPROVAL → APPROVED | Owner selected: thumbnail, final title, `privacyStatus` (explicit), `selfDeclaredMadeForKids` (explicit), `containsSyntheticMedia` (confirmed), publish time (optional). If Private-only mode is ON, privacy must be `private` and no `publishAt`. Approval record stores a hash of the exact metadata + render + thumbnail. | OWNER [S][F] |
| APPROVED → UPLOADING | Approval hash == current package hash (any change after approval invalidates it). Channel ACTIVE. Publishing kill switch OFF (for public or scheduled). | ORCH |

### What "auto-fixable" means (RENDERING → ASSEMBLY)
Loudness out of range (re-normalise), a small A/V drift (re-mux), or a missing caption track. After two loops the project goes to `FAILED` and the owner is notified.

## 4. Render Job

```mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> WAITING_RESOURCES : RAM/disk insufficient OR outside night window (final long-form)
    WAITING_RESOURCES --> QUEUED : SYSTEM re-check OK
    QUEUED --> RUNNING : heavy worker picks job
    RUNNING --> SEGMENT_DONE : segment n rendered (checkpoint)
    SEGMENT_DONE --> RUNNING : next segment
    SEGMENT_DONE --> CONCATENATING : all segments done
    CONCATENATING --> QC_CHECK
    QC_CHECK --> SUCCEEDED : QC pass
    QC_CHECK --> QC_FAILED : QC fail
    RUNNING --> RETRYING : transient error / OOM
    RETRYING --> QUEUED : backoff elapsed (lower-memory preset on OOM)
    RETRYING --> FAILED : attempts exhausted (max 2)
    RUNNING --> CANCELLED : Emergency Stop / OWNER (process killed, work dir cleaned)
    SUCCEEDED --> [*]
    QC_FAILED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

Resume after a crash restarts from the last `SEGMENT_DONE` checkpoint. Proxy renders use the same machine with `kind = PROXY` (single segment, no night window).

## 5. Upload Job

```mermaid
stateDiagram-v2
    [*] --> PREFLIGHT
    PREFLIGHT --> REJECTED : invariant violated (privacy unset, audit not passed, no/invalid approval, kill switch)
    PREFLIGHT --> WAITING_QUOTA : bucket insufficient
    WAITING_QUOTA --> PREFLIGHT : PT midnight reset
    PREFLIGHT --> SESSION_STARTED : quota reserved, resumable session URI persisted
    SESSION_STARTED --> TRANSFERRING
    TRANSFERRING --> TRANSFERRING : chunk ok (offset persisted)
    TRANSFERRING --> RESUMING : network error / crash
    RESUMING --> TRANSFERRING : status query → offset
    RESUMING --> FAILED : session expired AND retries exhausted
    TRANSFERRING --> UPLOADED : video_id returned (idempotency complete)
    UPLOADED --> SETTING_THUMBNAIL
    SETTING_THUMBNAIL --> SETTING_CAPTIONS
    SETTING_CAPTIONS --> SETTING_PLAYLIST
    SETTING_PLAYLIST --> POLLING_PROCESSING
    POLLING_PROCESSING --> COMPLETED : processingStatus=succeeded
    POLLING_PROCESSING --> PROCESSING_FAILED : processingStatus=failed/rejected
    REJECTED --> [*]
    COMPLETED --> [*]
    PROCESSING_FAILED --> [*]
    FAILED --> [*]
```

Notes:
- The DB enforces **one non-failed upload per (project_id, file_sha256)**. A second attempt reuses the existing job.
- If a session expired and the resumable upload cannot continue, a new session is created **only** after confirming via `videos.list` (owner's uploads, matching the title and the stored `upload_marker` in the description) that the first attempt did not finish. This prevents duplicates.
- Each `SETTING_*` step is retried on its own. On permanent failure the job completes with a warning and the owner is notified (for example, thumbnail rejected → set manually in Studio).

## 6. Notification

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> SUPPRESSED : dedup key seen within window / preference off
    CREATED --> DEFERRED : quiet hours AND severity < CRITICAL
    CREATED --> DIGEST_PENDING : channel prefers digest
    DEFERRED --> QUEUED : quiet hours end
    DIGEST_PENDING --> QUEUED : digest time (daily 09h00 / weekly Mon 09h00 Asia/Karachi)
    CREATED --> QUEUED
    QUEUED --> SENT : provider accepted
    QUEUED --> RETRYING : 429 / 5xx
    RETRYING --> QUEUED : backoff (respect retry_after)
    RETRYING --> FAILED : attempts exhausted (5) → fallback to in-app
    SENT --> READ : owner opens (in-app)
    SUPPRESSED --> [*]
    READ --> [*]
    FAILED --> [*]
```

Each delivery channel (in-app, Telegram, email) has its own delivery row with this state machine. In-app delivery is always created.

## 7. Approval Request (used by every OWNER gate)

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> APPROVED : OWNER (or auto-rule in FULLY-AUTO with rule ID recorded)
    PENDING --> CHANGES_REQUESTED : OWNER with comment
    PENDING --> REJECTED : OWNER
    PENDING --> EXPIRED : subject changed (hash mismatch) / timeout (default 14 days)
    APPROVED --> INVALIDATED : subject content changed after approval
```

The approval record stores: subject type and ID, **subject content hash**, actor, mode, rule ID (if auto), comment and timestamp. Downstream guards compare the hash.

## 8. Voice Profile (ADR-0019)

```mermaid
stateDiagram-v2
    [*] --> RECORDING_SAMPLES : OWNER starts (live mic only)
    RECORDING_SAMPLES --> CONSENT_PENDING : ≥ required sample minutes
    CONSENT_PENDING --> VERIFYING : OWNER reads consent text + one-time code
    VERIFYING --> READY : STT code match AND speaker-similarity ≥ threshold
    VERIFYING --> REJECTED : mismatch (logged as security event)
    READY --> DISABLED : OWNER
    DISABLED --> READY : OWNER
    READY --> DELETED : OWNER (profile + derived caches purged)
    DISABLED --> DELETED : OWNER
    REJECTED --> [*]
    DELETED --> [*]
```

## 9. Stock Purchase (ADR-0020, paid providers only)

```mermaid
stateDiagram-v2
    [*] --> QUOTED : OWNER selects asset; adapter returns price + licence
    QUOTED --> REFUSED : budget cap exceeded / provider disabled / editorial-only on monetised channel
    QUOTED --> CONFIRMED : OWNER confirms THIS purchase (price shown)
    CONFIRMED --> LICENSED : provider confirms licence
    LICENSED --> DOWNLOADED : file stored + rights record (licence proof) written
    CONFIRMED --> FAILED : provider error (no charge recorded)
    REFUSED --> [*]
    DOWNLOADED --> [*]
    FAILED --> [*]
```

Agents can never create a `CONFIRMED` transition. Only the `OWNER` actor is allowed, and this is enforced in the orchestrator **and** in the Stock adapter.

---

## 10. Test requirements for this document (Phase 5)
- Table-driven test per machine: every allowed transition succeeds with its guard satisfied, and fails with each guard violated individually.
- Every unlisted (from, event) pair is rejected.
- Emergency Stop: every transition except → PAUSED/CANCELLED is rejected.
- Idempotency: the same event twice → one transition row.
- Crash simulation: kill the worker between the state write and the job enqueue — impossible by design (same TX). Kill it during a job → the reconciler re-enqueues it exactly once.
- Approval hash invalidation: edit metadata after approval → APPROVED → UPLOADING is rejected.
