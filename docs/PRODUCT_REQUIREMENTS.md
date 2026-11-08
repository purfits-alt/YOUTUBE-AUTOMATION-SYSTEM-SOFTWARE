# TubeForge — Product Requirements Document (PRD)

**Version:** 1.2 (v1.0 approved at C1; v1.1 approved at C2; v1.2 adds owner-requested voice cloning and stock media at C2 — all 2026-11-08; see §11) · **Date:** 2026-11-08
**Sources:** `00_MASTER_PROMPT.md`, `PHASE0_VALIDATION_REPORT.md`, C0 answers in `PROJECT_PROGRESS.md`
**Requirement IDs** (`FR-…`, `NFR-…`, `US-…`) are stable. Later specs, tests and roadmap tasks refer back to them.

---

## 1. Vision

A local-first, free-to-run AI production studio. It helps one owner discover channel opportunities, then plan, produce, audit, publish and improve **original** YouTube videos across several channels. The owner stays in control throughout.

**Positioning:** *AI-assisted, owner-directed, quality-first.* TubeForge is not a mass-upload tool. It is built to help the owner make videos that viewers value and that YouTube's monetisation policies accept. **It does not and cannot guarantee views, growth or revenue.**

---

## 2. Context and constraints (from C0)

| Constraint | Value | Consequence |
|---|---|---|
| Owner machine | Windows 10, 8 GB RAM, no GPU (**H-LITE**) | Hybrid design: local DB, queue, render, TTS and STT; free-tier cloud for LLM text and images. One heavy job at a time. Native Windows install. |
| OS support status | Windows 10: general support ended 14 Oct 2025; consumer ESU reportedly extended to 12 Oct 2027 | Owner enrols in free consumer ESU; remaining risk accepted with mitigations (NFR-SEC-08) |
| Languages | EN, ES, FR, DE, UR supported; **launch in English, one channel** | Per-channel content language. Urdu needs RTL and is high-risk for local quality. |
| Timezone | Asia/Karachi (owner). YouTube quota day = Pacific Time | Times stored in UTC and shown in both zones where relevant |
| Access | Dashboard on `127.0.0.1` only | No remote or LAN access in v1 |
| Notifications | In-app + Telegram (email optional, off) | WhatsApp adapter disabled |
| Budget | **Zero recurring cost** | Free/local providers only. Paid adapters exist but are disabled. |
| Repository | `purfits-alt/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE`, **public** | No secrets in git, ever. Secret scanning in CI. |

---

## 3. Personas

### P1 — Owner ("CEO") — *primary, only user in v1*
- Runs 1 channel at launch and up to 10 later, from one Windows PC.
- Not necessarily a developer. Needs guided setup, plain-language errors and safe defaults.
- Goals: build channels that can be monetised, keep costs at zero, spend their own time on the creative parts (ideas, voice, insight) and let the system do the repetitive parts.
- Fears: losing a channel to a policy strike, surprise bills, the system publishing something embarrassing, losing work.

### P2 — Editor / Reviewer / Viewer — *future (post-v1)*
- Roles are defined in the data model from the start (RBAC). There is no team UI in v1.

### P0 — The viewer *(indirect stakeholder)*
- Every quality, originality and honest-metadata requirement exists to serve the viewer. If a video gives viewers no value, the system must not encourage publishing it.

---

## 4. Scope

### 4.1 In scope (v1)
The 25-step workflow in master prompt §2.4, covered by the epics in §6 below.

### 4.2 Explicit non-goals
| ID | Non-goal |
|---|---|
| NG-1 | Automatic YouTube channel creation (no API exists). Onboarding is guided and manual. |
| NG-2 | Scraping YouTube or Google Trends, downloading or reuploading third-party videos, automating YouTube Studio web pages |
| NG-3 | Fake engagement of any kind (views, likes, comments, subscribers) |
| NG-4 | Impersonating real people. Cloning any voice other than the owner's own, recorded with consent. |
| NG-5 | Misleading titles, thumbnails or metadata |
| NG-6 | Any claim or forecast that a niche or video **will** earn money |
| NG-7 | Paid services enabled by default, or any automatic upgrade to a paid plan |
| NG-8 | Remote/LAN dashboard access, multi-user team UI, mobile app (v1) |
| NG-9 | Long-form generative AI video (adapter interface only, disabled) |
| NG-10 | Local AI image generation on H-LITE (supported later on H1/H2 hardware via the same adapter) |

---

## 5. Operating modes (summary)

| Mode | Default? | Who approves publish | Preconditions |
|---|---|---|---|
| MANUAL | ✅ Yes | Owner approves every stage | — |
| SEMI-AUTOMATIC | No | Owner approves publication | Owner switches it on per channel |
| FULLY-AUTOMATIC | No | Rules set by the owner | ≥ N (default 10) successful private test runs **and** a verified public-release test on the test channel **and** two-step owner activation per channel **and** an owner-accepted auto-publish rule set (DP-6 express consent) |

**Private-only mode** is an owner safety switch (since 2 Nov 2026 YouTube no longer forces unverified API projects to private, see ADR-0016). It is ON by default for a new channel until 3 successful private test uploads, then the owner may switch it off. When ON, every upload is `private` and the owner makes videos public in YouTube Studio, and the UI shows a banner. **Independently of this switch, `privacyStatus` is always sent explicitly, because an omitted value now defaults to public.**

---

## 6. Epics and user stories

Format: *As the owner, I want … so that …*. Each story has testable acceptance criteria (AC). "Phase" is the build phase that delivers it (preliminary, finalised in the roadmap).

### E1 — Foundation, login and safety controls

**US-1.1 Owner login** (Phase 3)
As the owner, I want a secure local login so that only I can control my channels.
- AC1: Passwords are hashed with Argon2id. Plain passwords are never stored or logged.
- AC2: Optional TOTP 2FA can be enabled. After enabling, login requires a valid code.
- AC3: After 5 failed logins within 15 minutes, the account locks for 15 minutes and a security event is logged.
- AC4: The server binds only to `127.0.0.1`. A request from another host is refused.

**US-1.2 Emergency Stop** (UI Phase 2, enforced Phase 5)
As the owner, I want one button that stops everything so that I can halt the system instantly if something looks wrong.
- AC1: The button is visible on every page.
- AC2: When pressed, no new job starts. Running jobs stop at the next safe checkpoint within 30 s. No upload or publish call starts after the stop time.
- AC3: The stop is logged with time and user. Resuming needs an explicit confirmation.

**US-1.3 Kill switches** (Phase 5)
As the owner, I want separate switches per channel, per agent, per provider and for publishing, so that I can stop one part without stopping everything.
- AC: Each switch takes effect immediately, is logged, and is shown on every page as a status badge.

**US-1.4 Audit trail** (Phase 3)
As the owner, I want every write, agent action, approval and cost recorded so that I can see who did what and when.
- AC1: Every API write creates an audit-log row (actor, action, entity, before/after hash, time).
- AC2: The audit log is append-only through the API. No endpoint can edit or delete it.

### E2 — Channel discovery and strategy

**US-2.1 Niche discovery** (Phase 6)
As the owner, I want a ranked list of niche opportunities with evidence so that I can choose a direction based on data, not hype.
- AC1: Each niche shows an Opportunity Score made of named criteria (value, weight, evidence link, confidence).
- AC2: The owner can change weights, and scores recalculate immediately.
- AC3: Every niche shows an **inauthentic-content risk** and a **production difficulty on H-LITE** rating.
- AC4: No text anywhere states or implies guaranteed earnings. A test scans outputs for forbidden phrases.
- AC5: Data comes only from permitted sources listed in the provider registry. **Scores are not computed from aggregated YouTube API data about other channels** (ADR-0015). Sources: Wikipedia pageviews, RSS/news, Google Trends API (alpha, only if the owner is accepted), owner's own channel analytics, LLM reasoning with citations.

**US-2.2 Trend intelligence** (Phase 6)
As the owner, I want rising topics in my niche from permitted sources so that I can make timely videos.
- AC: Each trend has its source, the time it was fetched, a confidence level, and an expiry. Expired trends are hidden by default.

**US-2.3 Competitor research** (Phase 6) — *revised for Developer Policies (ADR-0015)*
As the owner, I want to look up a channel or video I name and see its public information, so that I can study it myself.
- AC1: Uses only official API metadata. Never downloads videos or thumbnails for reuse.
- AC2: Shows each looked-up item **individually**. **No cross-channel statistics, rankings or aggregated pattern scores built from YouTube API data** (Developer Policies: Data Aggregation).
- AC3: Non-authorized data is cached ≤ 30 days, then deleted or refreshed automatically.
- AC4: Every API call is charged to the quota ledger (search.list has its own 100/day bucket). Research may use at most a configurable share (default 30 %) of each bucket.

**US-2.4 Channel blueprint** (Phase 6)
As the owner, I want a full channel plan from a chosen niche so that I can launch with a clear strategy.
- AC: The blueprint includes name ideas (marked "check availability manually"), description, brand brief, logo and banner briefs, audience, content pillars, formats, a 30-day calendar, 50 ideas, competitor summary, and risks. All sections are editable, and the blueprint is versioned.

### E3 — Channel onboarding and YouTube connection

**US-3.1 Guided channel creation** (Phase 4)
As the owner, I want step-by-step instructions to create the channel myself, since no API can create it.
- AC: A checklist with links to official YouTube Help. Each step can be marked done. Progress is saved.

**US-3.2 Google Cloud and OAuth setup guide** (Phase 4)
As the owner, I want guided setup of my Google Cloud project and OAuth client so that I can connect without being a developer.
- AC: The guide covers creating the project, enabling the APIs, the consent screen, test users, the OAuth client, and where to paste the client ID. It warns that Testing-mode tokens expire after about 7 days (to be verified).

**US-3.3 Connect a channel** (Phase 4)
As the owner, I want to connect a channel through Google sign-in so that TubeForge can work with it.
- AC1: OAuth uses the minimum scopes needed for the enabled features.
- AC2: Tokens are encrypted at rest (AES-GCM). The key comes from the Windows Credential Manager / OS keyring, not from `.env`.
- AC3: After connecting, the channel ID and title are shown and the owner must confirm they are the intended ones.
- AC4: Disconnecting revokes the token with Google and deletes it locally. All stored API data for that channel is deleted within 7 days (Developer Policies), with a deadline monitor.

**US-3.4 Token health** (Phase 4)
As the owner, I want to be warned before the connection breaks so that uploads don't fail silently.
- AC: An expired or revoked token sets the channel to `needs_reauth`, blocks YouTube jobs for that channel, and raises an in-app notification (Telegram from Phase 14) with a one-click re-authorise link.

**US-3.5 Test upload** (Phase 4)
As the owner, I want a private test upload to my test channel so that I know the connection works.
- AC: Uploads a small generated test clip as `private`, with `containsSyntheticMedia` set explicitly and `is_test=true`. It is allowed only on channels marked as test channels. The video ID is shown.

### E4 — Ideas, research and scripts

**US-4.1 Idea generation** (Phase 7)
As the owner, I want idea suggestions tied to my channel strategy so that I always have a backlog.
- AC1: Each idea has a title, angle, target viewer, format (long or Short), originality notes, and a similarity score against the channel's existing ideas and videos.
- AC2: Ideas too similar to existing ones (above a configurable threshold) are flagged.

**US-4.2 Research brief with citations** (Phase 7)
As the owner, I want a research brief with sources for each idea so that my videos are accurate.
- AC1: Every factual claim links to at least one source, with the date fetched.
- AC2: Fetched web content is treated as untrusted data (prompt-injection policy). Fetching uses an allowlist and blocks private IPs.

**US-4.3 Fact-check** (Phase 7)
As the owner, I want claims in the script checked against sources so that I don't publish false information.
- AC: Each claim is marked `supported`, `unsupported`, `contradicted` or `opinion`. A script with any `contradicted` claim cannot leave SCRIPT_REVIEW without an owner override with a written reason.

**US-4.4 Script writing and versions** (Phase 7)
As the owner, I want AI-drafted scripts that I can edit, with version history, so that the final words are mine.
- AC1: Every save creates a version. Any two versions can be compared.
- AC2: The script has a hook section, a body and a call to action, plus an estimated spoken duration for the channel language.
- AC3: **Owner value-add fields** (own opinion, own experience, own data, own examples) are shown in the editor. The amount filled in feeds the originality score.

### E5 — Storyboard, visuals and voice

**US-5.1 Storyboard** (Phase 8)
- AC: The script is split into scenes with narration text, visual instruction, on-screen text, and duration. Scenes can be edited, reordered and regenerated one at a time.

**US-5.2 Visual assets with rights records** (Phase 8)
As the owner, I want visuals for every scene and a recorded right to use each one.
- AC1: Supported sources: procedural graphics, charts, kinetic text, owner uploads, CC0/public-domain imports, free-tier image APIs whose licence allows monetised use, and **stock video/images (optional, ADR-0020)**:
  - **Manual licensed import** from any free or paid stock site (file + licence type + licence proof + cost), always available.
  - **Free stock API adapters** (Pexels, Pixabay), off by default, owner's own API key.
  - **Paid stock API adapters** (Shutterstock, Adobe Stock, Storyblocks, Pond5, Getty/iStock), disabled by default, two-step activation, price shown and separate owner confirmation for **every** licence purchase, monthly stock budget cap (default 0). Agents can never buy.
- AC2: **No asset can enter a render without a rights record** (source, licence, commercial-use flag, attribution text, proof URL or file).
- AC3: Providers or licences that do not allow commercial use (incl. **editorial-only** stock) are blocked for channels marked as monetised.
- AC4: The Originality Auditor warns when stock footage exceeds a configurable share of runtime (default 60 %) without owner narration or commentary (reused-content risk).

**US-5.3 Voiceover** (Phase 8) — *extended at C2 (ADR-0019)*
As the owner, I want to record my own voice, **or generate narration in a clone of my own voice**, or use a licensed TTS voice.
- AC1: In-browser recording with level meter, retake per scene, and noise reduction.
- AC2: TTS voices come from the registry with their licence recorded. Each language shows which voices are available, and a missing language (e.g. Urdu, if none is found) is shown clearly.
- AC3: **Owner voice clone** is available in two modes: *converter* (Kokoro/Piper → OpenVoice V2 tone-colour conversion; all 5 languages) and *zero-shot* (Chatterbox Multilingual; EN/ES/FR/DE). Both are local and free.
- AC4: A voice profile can be built **only from audio recorded live in TubeForge** (no file upload). The owner reads a consent statement with a random one-time code. STT verifies the code, and a speaker-similarity check confirms the consent audio and the samples are the same person. The consent record is stored.
- AC5: Voice profiles are encrypted at rest, never exported, never sent to cloud providers, and deletable with one click (including derived audio).
- AC6: Using the owner's own clone does not by itself set `containsSyntheticMedia` (YouTube Help 14328491). The disclosure assessment logs this reason.
- AC7: Cloning anyone other than the owner is impossible by design and forbidden (NG-4).

### E6 — Editing and rendering

**US-6.1 Timeline and preview** (Phase 9)
- AC1: The timeline is stored as JSON. Rendering the same timeline twice gives the same streams, duration and resolution.
- AC2: Low-resolution proxy preview in the browser.

**US-6.2 Long-form and Shorts render** (Phase 9)
- AC1: Long-form 16:9. Shorts 9:16, at most the current Shorts maximum length (to be verified).
- AC2: Audio is normalised to the configured loudness target (default −14 LUFS integrated, to be verified).
- AC3: An ffprobe-based QC report checks duration, streams, resolution, frame rate, loudness, black/frozen frames and silence gaps.
- AC4: On H-LITE, renders run one at a time, can be scheduled for night hours, and can resume or restart after a crash.

**US-6.3 Captions** (Phase 9/10)
- AC: Subtitles come from the script and are aligned with faster-whisper, exported as SRT/VTT, and editable. Urdu captions always need owner review.

### E7 — Thumbnails and SEO

**US-7.1 Thumbnails** (Phase 10)
- AC1: At least 3 variants, with text overlays from the channel's brand kit.
- AC2: Checks for dimensions, file size and format (current YouTube limits, to be verified), plus a readability preview at small mobile size.
- AC3: The owner picks the final thumbnail. No competitor thumbnails are used as input.

**US-7.2 SEO package** (Phase 10)
- AC1: Several title options with character counts, plus description, tags, hashtags and chapters.
- AC2: Chapter timestamps are checked against the final render's duration.
- AC3: **Made-for-kids is always set by the owner.** Upload is blocked while it is unset.
- AC4: An **AI-disclosure assessment** produces a `containsSyntheticMedia` value with a reason. The owner confirms it. It is never left unset.
- AC5: A check flags metadata that doesn't match the video content (misleading-metadata check).

### E8 — Auditing and policy

**US-8.1 Independent audits** (Phase 11)
As the owner, I want content, copyright, policy, quality and thumbnail audits before upload so that bad videos never reach YouTube.
- AC1: Each audit reports result, score, failure reason, affected component, responsible agent, evidence and remediation.
- AC2: A critical failure moves the project to `BLOCKED`. **An automated test proves a blocked project cannot be uploaded** through any API path.
- AC3: The owner can override with a written reason, which is logged. Production agents can never override.

**US-8.2 Originality and repetition guard** (Phase 11)
As the owner, I want warnings when my channel looks templated or mass-produced so that I protect monetisation.
- AC1: Similarity against the channel's own catalogue (script text, structure, thumbnails, titles).
- AC2: Per-channel publishing caps (default: at most 1 long-form/day and 7/week; Shorts 2/day; owner-configurable).
- AC3: A video with zero owner value-add fields and TTS narration gets a **high inauthentic-content risk** warning. Blocking it is owner-configurable and on by default for SEMI/FULLY-AUTOMATIC modes.

### E9 — Upload and publishing

**US-9.1 Resumable upload** (Phase 12)
- AC1: Resumable upload continues after a network failure or restart.
- AC2: **No duplicate uploads.** A unique key on (project, file hash) is enforced in the database.
- AC3: Privacy status is set explicitly on every upload. Default is `private`.
- AC4: Thumbnail and captions are set after upload. Partial failures are retried on their own without re-uploading the video.

**US-9.2 Scheduling** (Phase 12)
- AC: `publishAt` is used only with `private` status. Scheduling a public release needs an owner approval record (or an owner-accepted auto-publish rule in FULLY-AUTO). Disabled while Private-only mode is ON. Times are shown in Asia/Karachi and in the channel's audience timezone.

**US-9.3 Quota ledger** (Phase 4, extended in Phase 12)
- AC1: Every YouTube API call records its unit cost, read from config.
- AC2: The ledger tracks **three buckets**: `videos.insert` (100 calls/day), `search.list` (100 calls/day), and the shared 10,000-unit pool. A job that would exceed the remaining quota of any bucket it needs (with a safety reserve, default 10 %) does not start. It is rescheduled after the Pacific-midnight reset, and the owner is notified.

**US-9.4 Privacy policy & optional audit package** (Phase 4 policy, Phase 12 package)
- AC1: A privacy policy and terms template meeting Developer Policy III.A.2 (links to the Google Privacy Policy and `security.google.com/settings/security/permissions`) is ready before the first OAuth connection.
- AC2: A compliance-audit package (only needed for a quota extension) can be generated from templates for the owner. The system never submits anything on its own.

### E10 — Analytics and improvement

**US-10.1 Analytics** (Phase 13)
- AC: Daily snapshots of views, watch time, average view duration, CTR (when available), subscribers gained/lost and traffic sources. Own-channel analytics may be kept long-term, but **authorization and video existence are re-checked at least every 30 days** (Developer Policies III.E.4). No monetary metrics in v1 (D-8).

**US-10.2 Growth suggestions** (Phase 13)
- AC: Suggestions (e.g. better hooks, topics, upload times) each cite the data behind them. **None is applied without owner approval.**

**US-10.3 Comment moderation assistant** (Phase 13)
- AC: Suggests replies or flags spam. Every action needs owner approval. It needs a broader scope, so it is off by default and the scope is requested only when the owner enables it.

### E11 — Notifications

**US-11.1** (in-app from Phase 4; Telegram, digest and dedup in Phase 14)
- AC1: Events and channels follow master prompt §12. Each event type can be turned on or off per notification channel.
- AC2: Quiet hours in Asia/Karachi (default 23:00–08:00). Critical alerts (OAuth broken, quota exhausted, Emergency Stop) bypass quiet hours.
- AC3: A deduplication key stops the same event being sent twice within its window. Daily and weekly digests are available.

### E12 — Cost, usage and providers

**US-12.1 Provider registry** (Phase 5)
- AC: Every provider and model has a record: tier (L/F/P), limits, licence, commercial-use flag, data-use/training note, verification URL and date. A provider with no verification date for over 90 days shows a "re-verify" warning.

**US-12.2 Hard usage limits** (Phase 5)
- AC1: Daily and monthly limits per provider and per task are enforced locally **before** the call is made.
- AC2: At the limit, related tasks pause. A configured free fallback is used if one exists. The owner is notified.
- AC3: **A test proves a provider pauses at its limit.**

**US-12.3 Paid providers impossible by accident** (Phase 5)
- AC: Tier-P adapters are disabled in code. Enabling one needs two separate confirmed actions, shows the estimated cost before every use, and is logged. No payment credentials are ever stored.

**US-12.4 Cost & Usage dashboard** (Phase 5)
- AC: Shows usage against the limit for every provider, the YouTube quota with forecast, disk usage, and render queue time.

### E13 — Operations

**US-13.1 Backup and restore** (Phase 15)
- AC: One-click and scheduled backup (database dump, encrypted secrets, project metadata; media optional) to a folder the owner chooses (e.g. an external drive). Restoring to a clean install is tested.

**US-13.2 Disk management** (Phase 9/15)
- AC: Disk usage per channel and project. Warnings at 80 % and 90 % of a configured budget. Cleanup removes intermediate files only, never final masters, and only after owner confirmation.

**US-13.3 Install on Windows** (Phase 1/15)
- AC: A documented native install (PostgreSQL, Python, FFmpeg) with a start script. The installer checks for at least 60 GB of free disk and 8 GB of RAM and warns if either is missing. Verified on a clean Windows 10 machine (or VM).

---

## 7. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-COST-01 | Cost | Running costs €0/month in the default configuration. CI runs on the GitHub Actions free tier (public repo). |
| NFR-PERF-01 | Resources | Idle memory footprint of all TubeForge services ≤ 1.5 GB on H-LITE (target, to measure in Phase 1). |
| NFR-PERF-02 | Resources | At most one heavy job (render, STT, local LLM) at a time. The others queue. |
| NFR-PERF-03 | UX | Dashboard pages load in < 2 s on localhost with typical data. |
| NFR-REL-01 | Reliability | Every workflow transition is persisted. After a crash or restart, work resumes from the last completed step with no duplicate side effects (idempotency keys). |
| NFR-REL-02 | Reliability | External calls have timeouts, classified errors and bounded retries with backoff. |
| NFR-SEC-01 | Security | No secrets in git. Secret scanning runs in pre-commit and CI. The repo is public. |
| NFR-SEC-02 | Security | OAuth tokens and provider keys are encrypted at rest. The encryption key is in the OS keyring. |
| NFR-SEC-03 | Security | Localhost binding, CSRF protection, secure session cookies, Argon2id. |
| NFR-SEC-04 | Security | Untrusted content (web, RSS, comments) is never given tool access or treated as instructions. |
| NFR-SEC-05 | Security | Models are loaded only from safetensors or another non-executable format, with pinned hashes. |
| NFR-SEC-06 | Security | Dependency audit (`pip-audit`, `npm audit`) runs in CI and fails on high-severity issues. |
| NFR-SEC-07 | Security | Every DB query on channel data is scoped by channel and permission, with tests. |
| NFR-SEC-08 | Security | Windows 10 EOL risk is recorded in the risk register, with mitigations in the deployment guide. |
| NFR-PRIV-01 | Privacy | YouTube API data retention and deletion follow the Developer Policies (verified in 0.3). |
| NFR-PRIV-02 | Privacy | Text sent to cloud providers whose terms allow training is labelled in the UI. The owner can mark a channel "local-only" to block those providers. |
| NFR-COMP-01 | Compliance | Official YouTube APIs only. No scraping (tests make sure no HTTP client targets youtube.com HTML pages). |
| NFR-I18N-01 | i18n | UI strings are externalised. Content languages EN/ES/FR/DE/UR. RTL rendering for Urdu text in thumbnails and captions. |
| NFR-A11Y-01 | Accessibility | Dashboard targets WCAG 2.2 AA (keyboard navigation, contrast, labels). |
| NFR-OBS-01 | Observability | Structured JSON logs with PII and secret redaction. Agent-run logs searchable in the UI. |
| NFR-MAINT-01 | Maintainability | Python: ruff + mypy (strict) + pytest. TypeScript: eslint + prettier + tsc strict. Each phase ends with passing tests. |
| NFR-PORT-01 | Portability | Primary target Windows 10/11 native. Linux supported (dev/CI). macOS best-effort. |

---

## 8. Success metrics (product, not revenue)

| Metric | Target (first 90 days after launch) |
|---|---|
| Zero-cost operation | €0 spent, 0 accidental paid calls |
| Safety | 0 videos uploaded that failed a blocking audit. 0 unintended public videos. |
| Reliability | ≥ 95 % of pipeline runs finish without manual DB repair. 0 duplicate uploads. |
| Owner time | Owner hands-on time per long-form video ≤ 3 h (measured from approval timestamps) |
| Throughput (H-LITE) | Able to finish ≥ 2 long-form + 4 Shorts per week for one channel within free-tier limits |
| Quality gate | ≥ 90 % of published videos have a non-empty owner value-add record |
| Policy | 0 Community Guidelines strikes caused by a TubeForge-generated asset or metadata |
| Learning loop | Growth suggestions reviewed weekly. Accept/reject ratio tracked. |

**Not a success metric:** revenue, subscriber count or views. These depend on factors outside the software and are shown in analytics only.

---

## 9. Assumptions

1. The owner will create a Google Cloud project, a separate **test channel**, and the real channel before Phase 4.
2. The owner has a stable internet connection for free-tier AI calls and uploads.
3. At least one free-tier cloud LLM with acceptable terms will be available (verified in 0.3). If not, a small local model is used and quality is lower.
4. The owner accepts slow renders (possibly overnight) on H-LITE.

## 10. Open questions for C1

| ID | Question | Proposed default |
|---|---|---|
| OQ-1 | Media retention: keep intermediate files for how long? | 30 days after publish, then offer cleanup. Final masters kept until the owner deletes them. |
| OQ-2 | Backup target and frequency? | Daily DB + secrets backup to a folder the owner chooses. Media backup is manual. |
| OQ-3 | Publishing caps defaults (US-8.2 AC2) acceptable? | Yes as written |
| OQ-4 | Block (vs. warn) high inauthentic-risk videos in MANUAL mode too? | Warn in MANUAL, block in SEMI/FULLY |
| OQ-5 | Quiet hours 23:00–08:00 Karachi OK? | Yes |
| OQ-6 | Owner hands-on time target of ≤ 3 h/video realistic for you? | Yes, adjust later |

---

## 11. Change log

| Version | Date | Change | Reason |
|---|---|---|---|
| 1.0 | 2026-11-08 | Approved at C1 | — |
| 1.1 | 2026-11-08 | Operating modes: audit precondition removed; Private-only mode becomes a safety switch; explicit `privacyStatus` invariant | YouTube revision history 2 Nov 2026 (F1 reversed), ADR-0016 |
| 1.1 | 2026-11-08 | US-2.1 / US-2.3: no cross-channel aggregation of YouTube API data | Developer Policies "Data Aggregation", ADR-0015 |
| 1.1 | 2026-11-08 | US-9.3: three quota buckets | Granular quota since 1 Jun 2026 (F2) |
| 1.1 | 2026-11-08 | US-3.3, US-10.1, US-9.4: 7-day deletion, 30-day re-authorization, privacy-policy content | Developer Policies III.A.2, III.E.4 |
| 1.1 | 2026-11-08 | Windows 10 ESU note | Consumer ESU reportedly extended to Oct 2027 |
| 1.1 | 2026-11-08 | Approved at C2 | — |
| 1.2 | 2026-11-08 | US-5.3: owner voice cloning (converter + zero-shot), consent and anti-misuse controls | Owner request at C2, ADR-0019 |
| 1.2 | 2026-11-08 | US-5.2: optional stock media — manual import, free API adapters, paid API adapters (disabled, budget cap 0) | Owner request at C2, ADR-0020 |
