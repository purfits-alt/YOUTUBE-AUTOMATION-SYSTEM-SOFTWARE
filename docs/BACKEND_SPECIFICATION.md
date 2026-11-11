# Backend API Specification

**Version:** 1.0 (approved at C4, 2026-11-08) · **Date:** 2026-11-08
**Base URL:** `http://127.0.0.1:8765/api/v1` · **Framework:** FastAPI (ADR-0002) · **Contract:** OpenAPI 3.1, generated from the Pydantic models. A TypeScript client is generated from it for the web app.
**Schema reference:** `DATABASE_SCHEMA.md` (entity fields) · **Security:** `OAUTH_SECURITY.md`

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Auth | Session cookie `tf_session`. Every non-GET request also needs `X-CSRF-Token`. Unauthenticated → 401. |
| Authorization | Every route declares `perm` (see §4 tables). Channel-scoped routes also check channel access. Denied → 403 + `security_events` PERMISSION_DENIED. |
| Content type | `application/json; charset=utf-8`. Uploads use `multipart/form-data` (≤ 4 GB, streamed to the CAS). |
| IDs | UUIDv7 strings |
| Times | ISO 8601 UTC (`2026-11-08T07:00:00Z`). Clients display them in the owner's timezone. |
| Pagination | Cursor: `?limit=50&cursor=<opaque>` → `{ "items": [...], "next_cursor": "..." \| null }`. Max limit 200. |
| Filtering / sorting | `?filter[state]=SCRIPTING&filter[format]=LONG&sort=-updated_at`. Only whitelisted fields per endpoint. |
| Search | `?q=` full-text on listed fields (PostgreSQL `tsvector` for scripts and ideas) |
| Errors | **RFC 9457 problem+json** `{type, title, status, detail, instance, code, errors?[{field,message}], request_id}`. `code` is stable (e.g. `GUARD_FAILED`, `QUOTA_WAIT`, `IMPLICIT_PRIVACY`). |
| Idempotency | Every POST that creates or triggers something accepts `Idempotency-Key` (UUID). Stored 24 h. A replay returns the first response (same status and body). Required on: approvals, uploads, purchases, transitions, renders. |
| Optimistic locking | PATCH/PUT on versioned entities requires `If-Match: "<version>"`. Mismatch → 412 `VERSION_CONFLICT`. |
| Commands vs CRUD | State changes are **commands**: `POST /…/{id}/commands/{command}`. They return `202 Accepted` + `{transition_id, job_ids}` when work is queued, or `200` when synchronous. States are never PATCHed directly. |
| Audit | Middleware writes an `audit_log` row for every successful write (actor, action = route name, entity, before/after hash). |
| Transactions | Each request = one DB transaction. A command transaction includes state change + transition row + audit + job enqueue (Procrastinate, same connection). |
| Delete | Soft delete (`deleted_at`) for (SD) tables. Hard delete for secrets, voice profiles (async purge) and API data under DP-2/3/4. `DELETE` returns 204. |
| Rate limiting | Login: 5 per 15 min. Others: 600/min (local abuse guard only). |
| Versioning | `/api/v1`. Breaking changes → `/api/v2`. The OpenAPI snapshot is committed, and CI fails on unreviewed contract diffs. |
| Health | `GET /healthz` (process alive, no auth) · `GET /readyz` (DB, keyring, disk, worker heartbeat; no auth, localhost only) |

### 1.1 Standard error codes

| HTTP | code | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Field errors in `errors[]` |
| 401 | `UNAUTHENTICATED` | No or expired session |
| 403 | `FORBIDDEN`, `CSRF_FAILED`, `REAUTH_REQUIRED` | Permission, CSRF, or step-up needed (sensitive action) |
| 404 | `NOT_FOUND` | Also returned for resources on channels the user can't access |
| 409 | `GUARD_FAILED`, `ILLEGAL_TRANSITION`, `DUPLICATE`, `EMERGENCY_STOP_ACTIVE`, `KILL_SWITCH_ACTIVE` | State-machine refusals. `detail` lists failed guards |
| 412 | `VERSION_CONFLICT` | If-Match mismatch |
| 422 | `IMPLICIT_PRIVACY`, `RIGHTS_MISSING`, `LICENCE_BLOCKED`, `BUDGET_EXCEEDED`, `AUDIT_BLOCKED`, `APPROVAL_STALE` | Business-rule refusals |
| 423 | `LOCKED` | Account locked |
| 429 | `RATE_LIMITED` | |
| 503 | `NOT_READY`, `QUOTA_WAIT` | Dependency down / waiting for quota (with `retry_after`) |

## 2. Real-time events (SSE)

`GET /api/v1/events/stream` (`text/event-stream`). Supports `Last-Event-ID` replay (events kept 24 h in `audit_log`-backed buffer). Heartbeat comment every 15 s.

| Event | Payload | Emitted when |
|---|---|---|
| `state.changed` | `{entity_type, entity_id, channel_id, from, to, actor}` | Any workflow transition |
| `job.progress` | `{job_id, kind, entity_id, pct, stage, eta_s}` | Render, upload, TTS, clone and agent progress (≤ 1/s per job) |
| `job.finished` | `{job_id, kind, status, error_code?}` | Job end |
| `approval.requested` | `{approval_id, subject_type, subject_id, channel_id}` | New PENDING approval |
| `notification.created` | `{notification_id, severity, title}` | In-app notification |
| `control.changed` | `{emergency_stop, publishing_kill_switch, kill_switches[]}` | Any switch change |
| `quota.updated` | `{gcp_project, bucket, used, limit, reset_at}` | After each ledger write (throttled 1/10 s) |
| `usage.updated` | `{provider_code, metric, used, limit}` | After each settlement (throttled) |
| `channel.health` | `{channel_id, token_status, expires_at?}` | Token health changes |

## 3. Shared schemas (Pydantic → OpenAPI components)

`Problem`, `Page[T]`, `ChannelOut`, `ChannelCreate`, `PublishingRules`, `NicheCandidateOut`, `TrendItemOut`, `IdeaOut/In`, `ProjectOut`, `ProjectCreate`, `ValueAddIn`, `ScriptVersionOut/In`, `ClaimOut`, `StoryboardOut/In`, `SceneIn`, `AssetOut`, `RightsIn`, `StockSearchResult`, `StockQuote`, `VoiceProfileOut`, `NarrationOut`, `TimelineIn/Out` (timeline.json), `RenderJobOut`, `ThumbnailOut`, `SEOPackageIn/Out`, `DisclosureOut/ConfirmIn`, `CaptionTrackOut`, `AuditReportOut`, `OverrideIn`, `ApprovalOut`, `ApprovalDecisionIn`, `UploadChoicesIn`, `UploadJobOut`, `QuotaStatusOut`, `AnalyticsSeries`, `SuggestionOut`, `NotificationOut`, `NotificationPrefsIn`, `AgentConfigOut/In`, `AgentRunOut`, `ProviderOut`, `UsageOut`, `BudgetIn/Out`, `AuditLogOut`, `SecurityEventOut`, `SettingsOut/In`, `HealthOut`.
JSON payload schemas (`timeline.json`, `channel_blueprint.json`, `research_brief.json`, `auto_publish_rules.json`, …) live in `packages/shared/schemas/` and are referenced in OpenAPI.

## 4. Endpoints

Legend: **Perm** = permission code (OAUTH_SECURITY §3) · 🔁 = `Idempotency-Key` required · 🔐 = step-up re-auth (password/TOTP within 5 min) · ⚙ = async (202 + job).

### 4.1 Auth & session

| Method | Path | Request → Response | Perm | Notes |
|---|---|---|---|---|
| POST | `/auth/login` | `{email,password}` → `{user, mfa_required}` | public | Sets cookies. Lockout rules. |
| POST | `/auth/mfa/verify` | `{code}` → `{user}` | session (pre-MFA) | |
| POST | `/auth/logout` | – → 204 | session | |
| GET | `/auth/me` | → `{user, roles, permissions, mfa_enabled}` | session | |
| POST | `/auth/reauth` | `{password, code?}` → 204 | session | Opens a 5-min step-up window |
| POST | `/auth/password` | `{current, new}` → 204 | session 🔐 | Revokes other sessions |
| POST | `/auth/mfa/enroll` | – → `{otpauth_uri, qr_svg}` | session 🔐 | |
| POST | `/auth/mfa/confirm` | `{code}` → `{recovery_codes[]}` | session | Shown once |
| DELETE | `/auth/mfa` | – → 204 | session 🔐 | |
| GET | `/auth/sessions` · DELETE `/auth/sessions/{id}` | list / revoke | session | |

### 4.2 System controls & settings

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/system/controls` | → `{emergency_stop, publishing_kill_switch, kill_switches[]}` | `dashboard.view` |
| POST | `/system/emergency-stop` 🔁 | `{reason}` → controls | `emergency.activate` |
| POST | `/system/emergency-stop/clear` 🔁🔐 | `{reason}` → controls | `emergency.clear` |
| POST | `/system/publishing-kill-switch` 🔁 | `{active, reason}` → controls | `publishing.control` |
| POST | `/system/kill-switches` 🔁 | `{scope, target_id, reason}` → KillSwitch | `controls.manage` |
| DELETE | `/system/kill-switches/{id}` | → 204 | `controls.manage` |
| GET/PUT | `/settings` | SettingsIn (quiet hours, night window, disk budget, timezone, defaults) | `settings.manage` (PUT needs If-Match) |
| GET | `/system/health` | → `{ram, disk_d_free_gb, queue_depth, workers[], db, keyring, windows_build, last_backup}` | `dashboard.view` |
| POST | `/system/backups` 🔁⚙ | `{kinds:["DB","SECRETS","MEDIA"]}` | `settings.manage` |
| GET | `/system/backups` | list | `settings.manage` |
| POST | `/system/backups/key-export` 🔐 | `{passphrase}` → key file download | `settings.manage` |
| POST | `/system/backups/{id}/restore-test` ⚙ | | `settings.manage` |

### 4.3 Dashboard & search

| Method | Path | Response | Perm |
|---|---|---|---|
| GET | `/dashboard/overview` | `{channels[], pipeline_counts_by_state, pending_approvals, alerts, quota, usage_top, upcoming_schedule, recent_activity}` | `dashboard.view` |
| GET | `/search?q=` | `{results:[{type, id, title, channel_id, snippet}]}` across channels, ideas, projects, assets, notifications | `dashboard.view` |

### 4.4 Channels, onboarding, OAuth

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/channels` | Page[ChannelOut] (filter: state, language, mode) | `channel.view` |
| POST | `/channels` 🔁 | ChannelCreate `{name, content_language, is_test_channel, is_monetised, from_strategy_id?}` → ChannelOut (state APPROVED) | `channel.manage` |
| GET/PATCH | `/channels/{id}` | ChannelOut (+ `oauth_status`) / `{name, audience_timezone, local_only, is_monetised, privacy_policy_url}` (If-Match; setting the privacy URL can complete CONNECTED → ACTIVE) | `channel.view` / `channel.manage` |
| DELETE | `/channels/{id}` 🔐 | 204 (requires DISCONNECTED or never connected) | `channel.manage` |
| POST | `/channels/{id}/commands/{cmd}` 🔁 | cmd ∈ `start-onboarding, pause, resume, disconnect, reconnect` (`disconnect` also 🔐). Illegal moves → 409 `INVALID_TRANSITION` | `channel.manage` |
| POST | `/channels/{id}/mode` 🔁🔐 | `{mode}`. FULLY_AUTOMATIC guards: test runs ≥ N, public-release test, auto rules accepted | `channel.mode` |
| POST | `/channels/{id}/private-only` 🔁🔐 | `{enabled}`. Disabling needs ≥ 3 private test uploads | `channel.mode` |
| GET/PUT | `/channels/{id}/publishing-rules` | PublishingRules (If-Match) | `channel.manage` |
| POST | `/channels/{id}/publishing-rules/accept-auto-rules` 🔁🔐 | `{rules_sha256}` → records DP-6 consent | `channel.mode` |
| GET | `/channels/{id}/onboarding` | `steps[]` | `channel.view` |
| PATCH | `/channels/{id}/onboarding/{step_code}` | `{status, notes}`; `CONNECT` and `TEST_UPLOAD` are set by TubeForge (409 `SYSTEM_STEP`) | `channel.manage` |
| GET/POST/DELETE | `/oauth/clients` | register the owner's OAuth client `{label, client_id, client_secret?, gcp_project_id?, publishing_status}` (secret write-only, stored encrypted); DELETE → 409 `CLIENT_IN_USE` while a channel uses it | `oauth.manage` |
| POST | `/oauth/youtube/start` 🔁 | `{channel_id, features[]}` → `{authorization_url, expires_at}` (scopes computed; `features` ⊆ upload, readonly, captions, playlists, metadata, comments, analytics) | `oauth.manage` |
| GET | `/oauth/callback` | browser redirect from Google → HTML page "Connected — return to TubeForge" | public (state-checked) |
| GET | `/channels/{id}/oauth/identity` | `{youtube_channel_id, title, handle}` of the signed-in account (`channels.list mine=true`, 1 unit) — shown before the owner confirms | `oauth.manage` |
| POST | `/channels/{id}/oauth/confirm-identity` 🔁 | `{youtube_channel_id}` must equal the fetched ID → state CONNECTED | `oauth.manage` |
| POST | `/channels/{id}/oauth/incremental` 🔁 | `{features[]}` → `{authorization_url}` | `oauth.manage` |
| GET | `/channels/{id}/oauth/health` | `{status, scopes, expires_hint, expiring_soon, last_refresh_at, last_error, publishing_status}` | `channel.view` |
| POST | `/channels/{id}/test-upload` 🔁⚙ | uploads the generated 5-s test clip, private, `is_test` → 202 UploadJobOut; preflight refusals → 409 `REFUSED_*` (503 `WAITING_QUOTA`); job `yt.upload` is created in the same transaction | `upload.execute` |
| POST | `/channels/{id}/delete-api-data` 🔁🔐 | creates a `data_deletion_tasks` row (OWNER_REQUEST, due ≤ 7 days) | `channel.manage` |

### 4.5 Niche discovery, trends, blueprints, competitor lookup, keywords

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| POST | `/niches/reports` 🔁⚙ | `{languages[], interests?, avoid[], weight_profile_id?}` → report | `research.run` |
| GET | `/niches/reports` · `/niches/reports/{id}` | list / detail with candidates | `research.view` |
| GET | `/niches/candidates/{id}` | candidate + criteria + evidence | `research.view` |
| POST | `/niches/candidates/{id}/commands/{cmd}` | `shortlist, dismiss` | `research.run` |
| POST | `/niches/rescore` | `{report_id, weights}` → candidates re-scored (sync, no LLM) | `research.run` |
| GET/POST/PUT | `/niches/weight-profiles` | weight profiles | `research.run` |
| POST | `/strategies` 🔁⚙ | `{niche_candidate_id}` → blueprint generation | `strategy.manage` |
| GET | `/strategies/{id}` · PATCH (If-Match, edits blueprint JSON) | | `strategy.view` / `strategy.manage` |
| POST | `/strategies/{id}/commands/{cmd}` 🔁 | `propose, approve, reject, new-version` | `strategy.manage` |
| GET | `/trends?channel_id=` | Page[TrendItemOut] (filter status, confidence) | `research.view` |
| POST | `/trends/scan` 🔁⚙ | `{channel_id}` | `research.run` |
| POST | `/trends/{id}/commands/{cmd}` | `dismiss, to-idea` | `research.run` |
| POST | `/lookups/youtube` 🔁 | `{kind: CHANNEL\|VIDEO\|SEARCH, query}` → single-item result(s), cached ≤ 30 d (ADR-0015) | `research.lookup` |
| GET | `/lookups/youtube` | recent lookups (non-aggregated list) | `research.lookup` |
| GET/POST/DELETE | `/channels/{id}/keywords` | keyword list with evidence | `research.run` |
| GET/POST/PATCH | `/research-sources` | source registry. Enabling a `REQUIRES_OWNER_APPROVAL` source needs 🔐 | `settings.manage` |
| POST | `/research-sources/{id}/test` | fetch the source once now; returns the stored documents | `research.run` |
| GET | `/research-sources/{id}/documents?limit=` | recent stored documents (title, URL, 300-character excerpt, expiry) | `research.view` |

*`/research-sources` implemented in Phase 6 (`api/v1/research.py`).* GET needs `research.view`; POST and PATCH need `settings.manage`.
- POST `{kind: RSS|WEB_ALLOWLISTED, slug, url, terms_url?}` creates `RSS:<slug>` or `WEB:<slug>`. The allowlist is exactly the URL's host. The source starts switched off as `REQUIRES_OWNER_APPROVAL`.
- POST rejects (422 `INVALID_URL`) anything that is not https on port 443, an IP literal, or a YouTube/Google host.
- PATCH `{enabled?, terms_verified?: true}`. Switching on an unapproved source needs re-auth and makes it `APPROVED`. `BLOCKED` sources cannot be switched on (409).
- Test-fetch errors:
  - 409 for `STOPPED`, `NOT_APPROVED`, `SOURCE_OFF` and `NOT_FETCHABLE`;
  - 422 `FETCH_BLOCKED` for an outbound-policy breach;
  - 502 `FETCH_FAILED` or `FEED_UNREADABLE` when the site fails.

*`/niches/*` and `/strategies` (POST, GET) implemented in Phase 6 step B (`api/v1/niches.py`):*
- **Starting work.** `POST /niches/reports` and `POST /strategies` need an `Idempotency-Key`. They answer 202 and queue `research.discover` or `research.blueprint` on the `agents` queue. While Emergency Stop is on they answer 409 `STOPPED`.
- **Blueprint precondition.** `POST /strategies` needs a SHORTLISTED candidate (409 `NOT_SHORTLISTED`). Its body is `{niche_candidate_id, owner_notes?}`, and it returns `{job_id, status}`.
- **Candidate responses** carry `footer` (the fixed estimate disclaimer), `band` (±10 or null), the criteria with weights and evidence links, and `originality_angles`.
- **Rescore.** `/niches/rescore` takes `weights` or `weight_profile_id` (exactly one). It stores the new scores; unknown criteria or weights outside 0–15 get 422 `INVALID_WEIGHTS`.
- **Weight profiles.** `PUT /niches/weight-profiles/{id}` takes `{name?, weights?, is_default?: true}`; one default at a time.
- **Reading blueprints.** `GET /strategies/{id}` returns the blueprint with `problems`, re-checked on every read. PATCH and the approval commands come in step D.

*`/lookups/youtube` implemented in Phase 6 step C (`api/v1/lookups.py`):*
- **POST** `{kind, query, channel_id?}` needs an `Idempotency-Key` and returns `{id, kind, query_key, items[], cached, fetched_at, expires_at, notice}`.
- **POST errors:**
  - 422 `INVALID_QUERY`;
  - 404 `NOT_FOUND_ON_YOUTUBE`;
  - 409 `STOPPED`, `NO_CONNECTED_CHANNEL`, `NEEDS_REAUTH` or `WAITING_QUOTA` (with `resets_at`);
  - 502 `YOUTUBE_ERROR`.
- **GET** lists the unexpired lookups, newest first, each on its own.
- Successful lookups are audited (`youtube.lookup`: kind, query key and whether the cache answered).

*Phase 6 step D:*
- **Editing a blueprint.** `PATCH /strategies/{id}` needs If-Match with the `etag` (428/412) and works on a DRAFT only (409 `NOT_EDITABLE`). The saved blueprint must match the schema (422 `BLUEPRINT_INVALID`). `niche` and `footer` cannot be edited; other rule problems may stay in a draft.
- **Commands** — `POST /strategies/{id}/commands/{propose|approve|reject|new-version}`:
  - `propose` and `approve` need zero problems (409 `BLUEPRINT_HAS_PROBLEMS`);
  - `approve` needs `{channel_name, is_test_channel = true}` and `channel.manage`. It creates the channel (APPROVED, publishing rules, not monetised, language from the niche), links the blueprint, marks the candidate CONVERTED and the candidate's other drafts SUPERSEDED;
  - `new-version` copies the blueprint into a new DRAFT.
- **Trends.**
  - `GET /trends?channel_id=&include_inactive=`: expired items are hidden by default, and shown as EXPIRED when included.
  - `POST /trends/scan` (Idempotency-Key) queues `research.trend_scan`.
  - `POST /trends/{id}/commands/{dismiss|to-idea}`: `to-idea` answers 409 `NOT_AVAILABLE_YET` until Phase 7.
- **Keywords** — `GET`, `POST` and `DELETE /channels/{id}/keywords`:
  - POST `{phrase}` adds the phrase now (201, 409 `DUPLICATE_KEYWORD`, 422 `FORBIDDEN_PHRASE`);
  - POST `{seeds}` queues A05 (202, Idempotency-Key).

### 4.6 Ideas & calendar

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/channels/{id}/ideas` | Page[IdeaOut] (filter state, format, pillar; q) | `content.view` |
| POST | `/channels/{id}/ideas` | IdeaIn (owner idea) | `content.edit` |
| POST | `/channels/{id}/ideas/generate` 🔁⚙ | `{count ≤ 20, format?, pillar?}` | `content.edit` |
| PATCH | `/ideas/{id}` | IdeaIn (If-Match) | `content.edit` |
| POST | `/ideas/{id}/commands/{cmd}` 🔁 | `shortlist, schedule{date}, approve, discard` (approve creates a project) | `content.approve` for approve, else `content.edit` |
| GET | `/channels/{id}/outliers` | Page[OutlierOut] own videos: `{youtube_video_id, title, published_at, views, engaged_views, ctr, avd_s, multiple, age_days}` — own analytics only (ADR-0015/0025) | `analytics.view` |
| GET | `/channels/{id}/replicate` | `{winners:[OutlierOut], variations:[IdeaOut]}` | `content.view` |
| POST | `/channels/{id}/ideas/replicate` 🔁⚙ | `{youtube_video_id (own), kind, note?}` → job; ideas with `source=REPLICATE`; 422 `TOO_SIMILAR` when similarity > threshold; 404 if the video is not the channel's own | `content.edit` |
| GET | `/calendar?from=&to=&channel_id=` | `{items:[{date, idea|project, state}]}` | `content.view` |
| PATCH | `/calendar/items/{id}` | `{date}` (drag & drop) | `content.edit` |

### 4.7 Projects (core workflow)

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/projects` | Page[ProjectOut] (filter channel_id, state, format, blocked; sort) | `content.view` |
| POST | `/projects` 🔁 | ProjectCreate `{channel_id, idea_id?, format, working_title, parent_project_id?}` | `content.edit` |
| GET | `/projects/{id}` | ProjectOut + allowed commands (computed from the state machine) + guard status | `content.view` |
| PATCH | `/projects/{id}` | `{working_title, target_duration_s, render_profile}` (If-Match) | `content.edit` |
| POST | `/projects/{id}/commands/{cmd}` 🔁 | cmd ∈ `start, approve-research, request-research-changes, approve-script, request-script-changes, approve-cut, request-cut-changes, retry, pause, resume, cancel, choose-fix-path{target}` → 202 `{transition_id, job_ids}` | `content.approve` for approve-*, `content.edit` otherwise, `project.cancel` for cancel |
| GET | `/projects/{id}/timeline-history` | transitions list | `content.view` |
| GET/PUT | `/projects/{id}/value-add` | ValueAddIn → score recomputed | `content.edit` |
| GET | `/projects/{id}/research` · `/research/{version}` | briefs | `content.view` |
| GET | `/projects/{id}/claims?subject=` | ClaimOut[] | `content.view` |
| POST | `/claims/{id}/override` 🔁 | `{reason ≥ 20}` | `content.approve` |
| GET | `/projects/{id}/script/versions` · `/versions/{v}` · `/diff?a=&b=` | versions / diff | `content.view` |
| POST | `/projects/{id}/script/versions` 🔁 | ScriptVersionIn (owner edit → new version) | `content.edit` |
| POST | `/projects/{id}/script/regenerate` 🔁⚙ | `{section?, instruction}` | `content.edit` |
| GET | `/projects/{id}/storyboard` | latest StoryboardOut | `content.view` |
| PUT | `/projects/{id}/storyboard` | StoryboardIn (new version, If-Match) | `content.edit` |
| POST | `/projects/{id}/storyboard/scenes/{scene_id}/regenerate` ⚙ | `{instruction}` | `content.edit` |

### 4.8 Assets, rights, stock, visuals

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/assets` | Page[AssetOut] (filter channel_id, project_id, kind, origin, rights_status: OK\|MISSING\|BLOCKED, q) | `asset.view` |
| POST | `/assets` (multipart) 🔁 | file + `{channel_id?, project_id?, kind, origin}` → AssetOut (rights MISSING until set) | `asset.edit` |
| GET | `/assets/{id}` · `/assets/{id}/content` (Range support) · `/assets/{id}/preview` | metadata / bytes / thumbnail-sized preview | `asset.view` |
| PUT | `/assets/{id}/rights` | RightsIn (licence, commercial flag, editorial_only, attribution, proof_asset_id) → validated against channel monetisation | `asset.edit` |
| DELETE | `/assets/{id}` | soft delete (refused if used in an approved timeline) | `asset.edit` |
| POST | `/projects/{id}/visuals/generate` 🔁⚙ | `{scene_ids[], style}` → procedural visuals (ADR-0010) | `content.edit` |
| POST | `/projects/{id}/scenes/{scene_id}/assign-asset` | `{asset_id, in_s, out_s, effect}` | `content.edit` |
| GET | `/stock/providers` | registry rows for STOCK (enabled, tier, configured) | `asset.view` |
| GET | `/stock/search?provider=pexels&q=&type=video\|image&orientation=` | StockSearchResult[] (previews only; no download) | `stock.search` (provider enabled) |
| POST | `/stock/import` 🔁⚙ | `{provider, provider_asset_id, channel_id?, project_id?}` → free-licence download + auto rights record | `stock.import` |
| POST | `/stock/manual-import` (multipart) 🔁 | file + licence proof file + `{provider_name, asset_ref, licence_type, cost?, currency?}` → asset + rights | `asset.edit` |
| POST | `/stock/purchases/quote` 🔁 | `{provider, provider_asset_id, licence_type}` → StockQuote `{price, currency, licence_terms_summary, budget_remaining}` | `stock.purchase` (Tier P enabled) |
| POST | `/stock/purchases/{id}/confirm` 🔁🔐 | `{quote_sha256}` → LICENSED → DOWNLOADED (⚙). **Owner only**, budget-checked | `stock.purchase` |
| GET | `/stock/purchases` | list with state, cost | `stock.purchase` |

### 4.9 Voice

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET/PUT | `/channels/{id}/voice-config/{language}` | `{source, tts_provider_code?, tts_voice_id?, voice_profile_id?, clone_mode?, speaking_rate}` | `voice.manage` |
| GET | `/voices/tts?language=` | available TTS voices with licence and commercial flag (blocked ones marked) | `voice.view` |
| POST | `/voices/tts/preview` | `{voice, text ≤ 300}` → audio (cached) | `voice.view` |
| POST | `/projects/{id}/narration/generate` 🔁⚙ | `{scene_ids?[]}` (uses voice config) | `content.edit` |
| POST | `/projects/{id}/scenes/{scene_id}/recordings/session` | → `{recording_token}` (single-use, 10 min) | `content.edit` |
| POST | `/projects/{id}/scenes/{scene_id}/recordings` (multipart) 🔁 | audio + `recording_token` → narration take (noise reduction ⚙) | `content.edit` |
| POST | `/narration/{id}/select` | choose take | `content.edit` |
| GET | `/voice-profiles` | own profiles | `voice.profile` (owner only) |
| POST | `/voice-profiles` 🔁 | `{label, engine}` → RECORDING_SAMPLES | `voice.profile` |
| POST | `/voice-profiles/{id}/samples/session` | → `{recording_token, prompt_text}` | `voice.profile` |
| POST | `/voice-profiles/{id}/samples` (multipart) | live recording + token | `voice.profile` |
| POST | `/voice-profiles/{id}/consent/start` | → `{consent_text, one_time_code, recording_token}` | `voice.profile` |
| POST | `/voice-profiles/{id}/consent` (multipart) ⚙ | consent recording + token → VERIFYING → READY/REJECTED | `voice.profile` |
| POST | `/voice-profiles/{id}/commands/{cmd}` | `disable, enable` | `voice.profile` |
| DELETE | `/voice-profiles/{id}` 🔐 | → DELETED + purge job | `voice.profile` |

### 4.10 Timeline, render, captions

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/projects/{id}/timeline` · `/timeline/versions` | latest / list | `content.view` |
| PUT | `/projects/{id}/timeline` | TimelineIn (validated: rights OK for every asset, durations) → new version | `content.edit` |
| POST | `/projects/{id}/timeline/assemble` 🔁⚙ | auto-assemble from storyboard + narration | `content.edit` |
| POST | `/projects/{id}/renders` 🔁⚙ | `{kind: PROXY\|FINAL, timeline_version_id}` | `render.run` |
| GET | `/renders` · `/renders/{id}` | Page[RenderJobOut] (filter state, kind, channel) incl. QC report | `content.view` |
| POST | `/renders/{id}/commands/{cmd}` 🔁 | `cancel, retry` | `render.run` |
| GET | `/projects/{id}/captions` | tracks | `content.view` |
| POST | `/projects/{id}/captions/generate` 🔁⚙ | `{languages[]}` | `content.edit` |
| PUT | `/captions/{id}` | edited SRT/VTT text → new asset, `OWNER_EDITED`, `owner_reviewed=true` | `content.edit` |

### 4.10a External editors (ADR-0021, optional)

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/external-editors` | registry with enabled flag, supports video/thumbnail, licence notes | `content.view` |
| PATCH | `/external-editors/{code}` | `{enabled, exe_path?, url?}` (exe path must exist and end in `.exe`; URL https) | `settings.manage` |
| POST | `/external-editors` | custom editor `{name, kind, supports_video, supports_thumbnail, launch_type, exe_path?, url?}` | `settings.manage` |
| POST | `/projects/{id}/external-edit` 🔁 | `{subject: VIDEO\|THUMBNAIL, editor_code, source: FINAL_RENDER\|PROXY\|THUMBNAIL_ID}` → session + hand-off path. Launches the exe or returns the URL to open. Project → EXTERNAL_EDITING for VIDEO. | `content.edit` |
| POST | `/external-edit-sessions/{id}/return` (multipart) 🔁 | exported file (or picks the file found in `return\`) + declaration JSON → asset + checks ⚙ | `content.edit` |
| POST | `/external-edit-sessions/{id}/cancel` | | `content.edit` |
| GET | `/external-edit-sessions?project_id=` | sessions | `content.view` |

### 4.11 Thumbnails, SEO, disclosure

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| POST | `/projects/{id}/thumbnails/generate` 🔁⚙ | `{count ≥ 3, aspect, concepts?[]}` | `content.edit` |
| POST | `/projects/{id}/thumbnails` (multipart) | owner-made thumbnail → checks run | `content.edit` |
| GET | `/projects/{id}/thumbnails` | with checks + small-size previews | `content.view` |
| POST | `/thumbnails/{id}/select` | | `content.approve` |
| POST | `/projects/{id}/seo/generate` 🔁⚙ | | `content.edit` |
| GET/PUT | `/projects/{id}/seo` | SEOPackageIn (new version, If-Match). Validation: lengths, chapters vs render | `content.edit` |
| POST | `/projects/{id}/seo/made-for-kids` 🔁 | `{made_for_kids: bool}` — **OWNER only** | `publish.decide` |
| GET | `/projects/{id}/disclosure` | DisclosureOut (recommended value + reasons) | `content.view` |
| POST | `/projects/{id}/disclosure/confirm` 🔁 | `{value: bool}` — OWNER confirms | `publish.decide` |

### 4.12 Audits & approvals

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/projects/{id}/audits` | latest report per type + history | `audit.view` |
| POST | `/projects/{id}/audits/run` 🔁⚙ | re-run (e.g. after fixes) | `content.edit` |
| GET | `/audits` | Page (filter result, type, channel, critical) — Policy Center | `audit.view` |
| POST | `/audit-reports/{id}/override` 🔁🔐 | OverrideIn `{reason ≥ 20}`. Refused for copyright-critical | `audit.override` (owner) |
| GET | `/approvals` | Page[ApprovalOut] (filter state=PENDING, subject_type, channel) | `approval.view` |
| GET | `/approvals/{id}` | with subject preview (render link, metadata, thumbnail, audit summary, diff since last approval) | `approval.view` |
| POST | `/approvals/{id}/decision` 🔁 | ApprovalDecisionIn `{decision: APPROVE\|REQUEST_CHANGES\|REJECT, comment?, subject_sha256, upload_choices?}` — `subject_sha256` must match the current subject (else 422 `APPROVAL_STALE`) | depends on subject (`publish.decide` for UPLOAD_PACKAGE) |

`UploadChoicesIn` = `{privacy_status: private|unlisted|public (required), publish_at?: datetime, made_for_kids: bool (required), contains_synthetic_media: bool (required), notify_subscribers: bool, playlist_ids?: [], caption_languages?: []}`. The server re-validates against ADR-0016 and the I-1…I-12 invariants.

### 4.13 Uploads, schedule, quota

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/uploads` · `/uploads/{id}` | Page[UploadJobOut] incl. steps and progress | `upload.view` |
| POST | `/uploads/{id}/commands/{cmd}` 🔁 | `retry-step{step}, cancel` (cancel only before TRANSFERRING completes) | `upload.execute` |
| GET | `/schedule?from=&to=&channel_id=` | scheduled and planned releases | `upload.view` |
| PATCH | `/schedule/{upload_id}` 🔁 | `{publish_at}` → `videos.update` (needs a new approval if changed by > 0 s) | `publish.decide` |
| GET | `/quota` | QuotaStatusOut per project and bucket: used, held, limit, reserve, reset_at (PT + PKT), 7-day forecast | `upload.view` |
| GET/PUT | `/quota/config` | method costs, limits, reserve %, research share (+ source URL, verified_at) | `settings.manage` |

### 4.14 Analytics & growth & comments

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/analytics/channels/{id}?from=&to=&metrics=` | AnalyticsSeries (channel level) | `analytics.view` |
| GET | `/analytics/videos/{youtube_video_id}?from=&to=` | per-video series | `analytics.view` |
| POST | `/analytics/refresh` 🔁⚙ | `{channel_id}` | `analytics.view` |
| GET | `/growth/suggestions?channel_id=` | SuggestionOut[] with evidence | `analytics.view` |
| POST | `/growth/suggestions/{id}/decision` 🔁 | `{decision: ACCEPT\|REJECT}` | `content.approve` |
| GET | `/channels/{id}/comment-suggestions` | list (feature off by default) | `comments.moderate` |
| POST | `/comment-suggestions/{id}/decision` 🔁 | `{decision, edited_reply?}` → executes via SafeYouTubeClient if approved | `comments.moderate` |

### 4.15 Notifications

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/notifications` | Page (filter unread, severity, channel) | session |
| GET | `/notifications/summary` | `{unread, critical_unread}` for the bell | session |
| POST | `/notifications/{id}/read` · `/notifications/read-all` | | session |
| GET/PUT | `/notifications/preferences` | matrix event_type × channel {enabled, digest} | session |
| PUT | `/notifications/targets/telegram` | `{bot_token, chat_id}` (write-only, encrypted) | `settings.manage` |
| POST | `/notifications/targets/telegram/test` | sends a test message | `settings.manage` |
| PUT | `/notifications/targets/email` | `{smtp_host, port, username, password, from, to}` (write-only) | `settings.manage` |
| GET | `/notifications/deliveries?notification_id=` | delivery tracking | `settings.manage` |

### 4.16 Agents

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/agents` | AgentConfigOut[] + 24 h stats (runs, success %, p50 latency, tokens) | `agents.view` |
| GET | `/agents/{code}` · PATCH (If-Match) | config: enabled, provider_chain, limits, prompt_version. **Auditor agents cannot be disabled via API** (only paused through a kill switch with reason) | `agents.view` / `agents.manage` |
| GET | `/agents/{code}/prompts` | prompt versions (read-only; changed via repo + migration) | `agents.view` |
| GET | `/agent-runs` · `/agent-runs/{id}` | Page[AgentRunOut] (filter agent, status, project); input and output (redacted) | `agents.view` |
| POST | `/agents/{code}/run` 🔁 | `{input}` → 202 `{job_id}`; queues a test run (`agent.run`). 409 `NO_HANDLER` for agents not built yet (Phase 5: only `T00_HELLO`) | `agents.manage` |

*Implemented in Phase 5 (`api/v1/agents.py`).* Pause/resume uses the AGENT kill switch (`/system/kill-switches`), so it is the same switch the orchestrator and workers enforce. A `PATCH` that names an unknown provider in the chain returns 409 `UNKNOWN_PROVIDER`.

### 4.17 Providers, usage, costs

| Method | Path | Request → Response | Perm |
|---|---|---|---|
| GET | `/providers` | ProviderOut[] (tier, enabled, licence, commercial, data-use, limits, verified_at, re-verify due) | `providers.view` |
| PATCH | `/providers/{code}` | `{enabled, limits}` (Tier L/F). Enabling a provider with `data_use_training=true` warns about local-only channels | `providers.manage` |
| PUT | `/providers/{code}/credentials` | `{secret}` write-only | `providers.manage` |
| POST | `/providers/{code}/paid-activation/step1` 🔐 | `{acknowledge_cost: true}` → shows estimated costs | `providers.paid` |
| POST | `/providers/{code}/paid-activation/step2` 🔁🔐 | `{confirm_phrase: "ENABLE PAID <code>", monthly_cap}` (separate request, ≥ 60 s after step 1) | `providers.paid` |
| POST | `/providers/{code}/verify` | `{verified_url, notes}` → updates verified_at | `providers.manage` |
| GET | `/usage?period=day\|month` | UsageOut per provider and metric vs limit | `providers.view` |
| GET/PUT | `/budgets` | BudgetOut[] / `{scope, provider_code?, month, cap_minor}` 🔐 for raising caps | `providers.paid` |
| DELETE | `/providers/{code}/credentials` | removes the stored key (one key per family) | `providers.manage` |
| POST | `/providers/{code}/paid-activation/disable` | switches a paid provider off at once (no re-auth: turning money off must never be hard) | `providers.paid` |
| GET | `/costs/summary` | month spend vs caps, paid providers enabled, banner text | `providers.view` |

*Implemented in Phase 5 (`api/v1/providers.py`).* Provider codes contain `:` and `/` (`groq:openai/gpt-oss-20b`). Routes take them with a path converter whose segments are never `verify`, `credentials` or `paid-activation`, so a code may be sent with a raw or `%2F`-encoded slash. Keys are stored per family (`gemini`, `groq`); Ollama needs none (409 `NO_KEY_NEEDED`). Enabling a Tier P provider through `PATCH` returns 409 `USE_PAID_ACTIVATION`. Saving limits clears the "placeholder" flag.

### 4.18 Audit & security

| Method | Path | Response | Perm |
|---|---|---|---|
| GET | `/audit-log` | Page[AuditLogOut] (filter actor, action, entity, channel, from/to) | `security.view` |
| GET | `/audit-log/verify-chain` | `{ok, first_broken_id?}` | `security.view` |
| GET | `/security-events` | Page (filter kind, severity) | `security.view` |
| GET | `/security/posture` | checks: TOTP on, keyring OK, token health, backups recent, last dependency audit, Windows ESU hint, outbound allowlist status | `security.view` |

## 5. Background jobs (Procrastinate task names)

| Queue | Task | Trigger |
|---|---|---|
| orchestrator | `orchestrate.on_event`, `orchestrate.reconcile` (every 2 min) | transitions / periodic |
| agents | `agent.run` (all 32 roles by `agent_code`) | orchestrator |
| heavy | `media.tts`, `media.voice_convert`, `media.voice_zero_shot`, `media.record_cleanup`, `media.stt_align`, `media.render`, `media.thumbnail_render`, `voice.verify_consent`, `voice.build_profile` | orchestrator / API |
| youtube | `yt.upload`, `yt.thumbnail`, `yt.captions`, `yt.playlist`, `yt.poll_processing`, `yt.track_publication`, `yt.test_upload`, `yt.comment_action` | orchestrator / API |
| notify | `notify.dispatch`, `notify.digest` (daily 09:00 PKT, weekly Mon) | events |
| maintenance | `mnt.token_health` (daily), `mnt.retention.*` (DATABASE_SCHEMA §15), `mnt.quota_forecast`, `mnt.health_sample` (1 min), `mnt.backup` (daily 03:00 PKT), `mnt.reverify_reminders`, `mnt.api_inactivity_check`, `mnt.disk_guard` | periodic |

## 6. Contract tests (Phase 3+)
- Schemathesis-style property tests against the committed OpenAPI: every endpoint returns documented status codes and schemas only.
- Authz matrix (route × role × channel scope).
- Idempotency: same key + same body → same response. Same key + different body → 422 `IDEMPOTENCY_MISMATCH`.
- Command guards: each `commands/{cmd}` with each failed guard → 409 `GUARD_FAILED` listing that guard.
- Every write produces exactly one `audit_log` row.
