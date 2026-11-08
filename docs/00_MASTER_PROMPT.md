# CLAUDE CODE MASTER PLANNING PROMPT
# Project: Independent AI YouTube Automation Platform (working name: **TubeForge**)
### Version 2.0 — Enhanced planning brief, free-tier-first, policy-compliant, phase-gated

---

## HOW TO USE THIS FILE (for the owner)

1. Create a new, empty folder for the project (e.g. `tubeforge/`) and run `git init` in it.
2. Save this file in that folder as `docs/00_MASTER_PROMPT.md`.
3. Open Claude Code in that folder and type:
   > Read `docs/00_MASTER_PROMPT.md` in full. Work in planning mode. Start Phase 0, Step 0.1, and stop at each OWNER CHECKPOINT for my approval.
4. Answer Claude Code's questions at each checkpoint. Do not let it write application code until you approve the full specification (Checkpoint C6).
5. After approval, start each build phase with a new message:
   > Implement Phase N from `docs/IMPLEMENTATION_ROADMAP.md`. Follow `CLAUDE.md`. Stop when the phase's acceptance tests pass and show me the results.

> **A note on the "$1 million" goal:** this prompt asks Claude Code to plan and build to the standard of a commercial SaaS product (clean architecture, tests, security, audit trails, multi-channel support). Software quality can be built. Channel revenue cannot be guaranteed. Revenue depends on audience, niche, originality and YouTube's monetization decisions. The platform must never claim it will earn money.

---

## 0. YOUR ROLE AND OPERATING RULES (for Claude Code)

You are acting as one coordinated team: Principal Software Architect, CTO, AI Agent Engineer, YouTube Platform & Policy Specialist, Full-Stack Developer, Product Manager, UI/UX Architect, Media Production Engineer, Security Engineer and QA Lead.

Your mission is to **plan, document and then build, phase by phase,** a complete, independent, production-grade AI YouTube media production and channel management platform.

### 0.1 Non-negotiable rules

1. **Plan before you code.** In Phase 0, write documentation only. Do not write application code until the owner approves the specification at Checkpoint C6.
2. **Independence.** This project is completely separate from SEMRS OS and any other existing product. Do not reuse its branding, database, agents, auth, APIs, notifications, infrastructure, code or deployment. TubeForge has its own repo, identity, credentials, config and deployment.
3. **Free-tier first.** Never use, enable or configure a paid API, subscription or service by default. See Section 3.
4. **Official APIs only.** Use only the official YouTube Data API v3, YouTube Analytics API and YouTube Reporting API for YouTube data and actions. Never scrape YouTube pages, never download competitor videos, never automate the YouTube Studio web UI.
5. **Verify, don't assume.** Anything about pricing, free-tier limits, quotas, licenses or platform policies changes often. Verify it from the official source during planning. Record the URL and the verification date. If you cannot verify something, mark it `UNVERIFIED` and design around the uncertainty.
6. **Be honest about limits.** If a capability cannot be done reliably for free (e.g. full long-form generative AI video), say so plainly. Build an adapter interface for it and leave the paid implementation disabled.
7. **Owner checkpoints are hard stops.** At every `OWNER CHECKPOINT`, stop, summarize what you produced, list open questions and wait for the owner's reply.
8. **Small, testable steps.** Each build phase ends with passing automated tests and a short demo script the owner can run.
9. **Decisions are recorded.** Every significant technology or design choice gets an Architecture Decision Record (ADR) in `docs/adr/` with the options considered, the free-tier status, the license and the reasons.
10. **Safety over automation.** When in doubt, the system pauses and asks the owner. It never publishes, spends money or deletes data on its own initiative outside owner-defined rules.

---

## 1. PLATFORM REALITY CHECK — FACTS THAT SHAPE THE DESIGN

These facts were checked on 2026-11-08. Re-verify each one in Phase 0 and record the result in `docs/FREE_TIER_PROVIDER_MATRIX.md` and `docs/YOUTUBE_API_INTEGRATION.md`.

| # | Fact | Design consequence |
|---|------|--------------------|
| F1 | Videos uploaded through `videos.insert` from **unverified API projects created after 28 July 2020 are restricted to private viewing**. Lifting this requires the project to pass a YouTube API compliance audit. | Phase 12 must ship with a "Private-only mode" that works before the audit. The roadmap must include preparing and submitting the YouTube API Services compliance audit, with the platform's privacy policy, terms and data-handling docs ready. Until the audit passes, the owner makes videos public manually in YouTube Studio, and the platform must say so clearly in the UI. |
| F2 | The default YouTube Data API quota is **10,000 units per day per Google Cloud project**, resetting at midnight Pacific Time. Official documentation pages currently disagree on the upload cost (some versions show 1,600 units per `videos.insert`, newer versions show a separate "Video Uploads" bucket). | Build a **quota ledger** that records the cost of every call, reads the current costs from config (not hard-coded), and blocks work before the quota runs out. In Phase 0, check the current cost in the official docs and in Cloud Console, and plan daily upload capacity from the worst case. `search.list` is expensive. Cache aggressively and prefer cheaper calls. |
| F3 | YouTube's YouTube Partner Program (YPP) treats **mass-produced, repetitive, "inauthentic" content** as ineligible for monetization (policy clarified July 2025 and enforced since). Examples at risk: automated voiceovers over stock images, near-identical templated videos, low-effort AI clips. | This is the **biggest business risk** of the whole product. The platform must be designed as **"AI-assisted, owner-directed, quality-first"**, not as a slop factory. Required features: originality and repetition scoring, per-channel publishing caps, mandatory owner value-add fields (own commentary, own insights, own data, own voice option), format-variety checks, and a Policy Auditor that blocks videos that look templated. |
| F4 | The Data API supports **`status.containsSyntheticMedia`** (added 30 October 2024) to declare realistic altered or synthetic content. It can be set on `videos.insert` and `videos.update`. | The SEO/Policy pipeline must run an "AI disclosure assessment" for every video and set `containsSyntheticMedia` explicitly on upload. Never leave it unset. Record the decision and reason in the audit log. |
| F5 | `status.publishAt` (scheduled publishing) can only be set while the video's privacy status is `private`. | The Scheduler uploads as `private` + `publishAt`. It depends on F1: scheduled public release only works after the audit. |
| F6 | The `youtube.upload` and related scopes are sensitive/restricted Google OAuth scopes. Google OAuth apps left in **"Testing"** publishing status issue refresh tokens that expire after about 7 days (verify current rule). | OAuth design must detect expired/revoked tokens, notify the owner, and support quick re-authorization. Document the steps to move the OAuth consent screen to "In production" and what Google verification is needed. |
| F7 | WhatsApp Business messaging is generally **not free** for business-initiated messages (verify current Meta pricing). | Telegram bot + email (SMTP) + in-app notifications are the free defaults. WhatsApp is an optional adapter, disabled by default, and it must show its cost status before the owner enables it. |
| F8 | Some popular "open" AI models have **non-commercial licenses** (for example, certain image and voice-cloning model weights). | The provider registry must record the license of every model and block models whose license doesn't allow use on a monetized channel. |
| F9 | Google Trends has no generally available free official API for this use, and unofficial libraries scrape it. | Do not depend on scraping. Evaluate official/permitted sources only: YouTube Data API (search, videos.list "mostPopular" chart by region/category), YouTube Analytics for owned channels, Wikipedia pageview API, Reddit official API (check terms), RSS/news feeds, Google Trends official API if it is available to the owner (verify). Any source with unclear terms is marked `REQUIRES OWNER APPROVAL`. |

---

## 2. PRODUCT VISION

### 2.1 One-sentence vision
A local-first, free-to-run AI production studio that helps one owner discover channel opportunities, plan, produce, audit, publish and improve original YouTube videos across multiple channels, with the owner always in control.

### 2.2 Product principles
1. **Owner in control.** Manual mode by default. Automation is earned through testing and switched on explicitly.
2. **Quality and originality over volume.** The system optimizes for viewer value and policy safety, not upload count.
3. **Evidence over hype.** Every niche score, trend claim and fact comes with sources and a confidence level.
4. **Rights are tracked for every asset.** No asset enters a render without a documented license or ownership record.
5. **Zero surprise costs.** Paid services are impossible to use by accident.
6. **Everything is auditable.** Every agent action, decision, cost and approval is logged and searchable.
7. **Replaceable parts.** AI models, TTS engines, image generators and notifiers are swappable adapters.

### 2.3 Primary user
A single owner (the "CEO") running 1–10 channels from their own computer. Later: optional team roles (Editor, Reviewer, Viewer).

### 2.4 End-to-end workflow (25 steps)
1. Discover niches → 2. Spot trending/emerging opportunities → 3. Generate channel concepts → 4. Plan name, branding, description → 5. Guide manual channel creation + connect via Google OAuth → 6. Find trending video ideas → 7. Research competitors and audience (official APIs only) → 8. Produce original ideas and scripts → 9. Fact-check with citations → 10. Storyboard → 11. Create original images/visual assets → 12. Generate authorized voiceover → 13. Assemble long-form videos → 14. Produce Shorts → 15. Generate thumbnails → 16. Create SEO titles, descriptions, tags, chapters → 17. Generate/sync subtitles → 18. Audit quality, copyright and policy → 19. Upload via official API (resumable) → 20. Set thumbnail and metadata → 21. Schedule publishing → 22. Pull analytics → 23. Improve using performance data → 24. Notify the owner → 25. Audit agents, activity, costs and operations.

### 2.5 Explicit non-goals
- No automatic YouTube channel creation (no supported API). Use a guided manual onboarding flow plus OAuth.
- No scraping, no downloading others' videos, no reuploading third-party content.
- No fake engagement (no bot views, likes, comments or subscribers).
- No impersonation of real people, no unauthorized voice cloning.
- No misleading titles/thumbnails.
- No promises of revenue or growth.

---

## 3. ZERO-COST / FREE-TIER POLICY

### 3.1 Protection rules (enforced in code, not just documentation)
1. No paid API is used by default.
2. No service is ever upgraded to a paid plan automatically.
3. Billing is never activated without explicit, logged owner permission.
4. No payment credentials are stored for automatic use.
5. Rate limits, tokens, storage and API quotas are monitored continuously.
6. Configurable daily, monthly and per-task usage limits exist for every provider.
7. When a provider reaches its free limit, the related tasks pause and the owner is notified.
8. An approved free/local alternative is used automatically when one is configured.
9. An owner-facing Cost & Usage dashboard shows every provider, its usage and its limit.
10. A **Provider Registry** records, for every provider/model: free-tier status, limits, license, commercial-use permission, data-privacy notes, and the last verification date and URL.

### 3.2 Provider tiers
- **Tier L (Local):** runs on the owner's machine (Ollama, local TTS, local image generation, FFmpeg). Always preferred.
- **Tier F (Free-tier cloud):** permanent free tiers only, with hard limits enforced locally.
- **Tier P (Paid / trial / promotional credit):** adapter may exist but is **disabled**, needs a two-step owner activation, and shows estimated cost before every use. A trial or promotional credit is **never** labeled "free".

### 3.3 Hardware profiles (ask the owner which applies at Step 0.1)
| Profile | Hardware | Expected capability |
|---|---|---|
| H0 | CPU only, 16 GB RAM | Small local LLMs (slow), local TTS, FFmpeg rendering, slideshow/motion-graphics videos; images via lightweight models or free-tier APIs |
| H1 | NVIDIA GPU 8 GB VRAM | 7–8B LLMs, SD 1.5/SDXL-class images (slow at SDXL), faster Whisper |
| H2 | NVIDIA GPU 12–24 GB VRAM | Larger LLMs, SDXL/FLUX-class images, faster everything |

The architecture must degrade gracefully between profiles: same features, different speed and quality settings.

---

## 4. TECHNOLOGY EVALUATION (do not adopt blindly)

For each area, compare at least 2–3 options on: **real free availability, license (and commercial-use rights), performance, Windows/macOS/Linux support, stability/maintenance, hardware needs, and ease of testing.** Write the comparison to `docs/TECH_STACK_EVALUATION.md` and one ADR per decision.

| Area | Candidates to evaluate (starting points only) |
|---|---|
| Frontend | Next.js + Tailwind CSS + shadcn/ui; alternatives: Vite + React; SvelteKit |
| Backend API | Python FastAPI + Pydantic + SQLAlchemy/SQLModel + Alembic; alternative: Django + DRF |
| Database | PostgreSQL (primary); SQLite only for tests/dev if justified |
| Task queue | Celery, Dramatiq, RQ, Arq, or a Postgres-backed queue (e.g. Procrastinate). Broker: Redis vs **Valkey** (check current Redis license vs Valkey's BSD license) |
| Orchestration | Custom state machine stored in Postgres vs LangGraph vs Temporal (check weight/complexity for a local install). Prefer the simplest design that gives durable, resumable workflows |
| Local LLM runtime | Ollama, llama.cpp server, LM Studio (check license for commercial use) |
| LLM models | Current open-weight instruct models suitable for the owner's hardware (e.g. Qwen, Llama, Mistral, Gemma families). Record each model's license |
| Free-tier LLM APIs | Evaluate current permanent free tiers (e.g. Google Gemini API free tier, Groq, OpenRouter free models, Mistral free tier). Record limits, data-use terms (some free tiers may use prompts for training) and verification date |
| Text-to-speech | Piper, Kokoro, other open TTS. Check each model/voice license. Voice cloning only of the owner's own voice, with recorded consent |
| Speech-to-text / subtitles | Whisper / faster-whisper / whisper.cpp |
| Image generation | ComfyUI or diffusers with permissively licensed models (check each model's license, e.g. some FLUX variants are non-commercial). Free-tier image APIs only if terms allow monetized use |
| Image processing | Pillow, OpenCV, rembg (check model license) |
| Video | FFmpeg (required), MoviePy or direct FFmpeg filter graphs; Remotion is an option for motion graphics but check its license terms for companies |
| Music & SFX | Owner-provided tracks, YouTube Audio Library (downloaded manually by the owner, license recorded), CC0 sources, procedurally generated music. Every track needs a rights record |
| Storage | Local filesystem with content-addressed layout; optional MinIO (check AGPL implications) or plain folders |
| Notifications | In-app (WebSockets/SSE), Telegram Bot API, SMTP email; WhatsApp optional/disabled |
| Auth (owner login) | Local accounts with Argon2 password hashing + optional TOTP 2FA; or a self-hosted auth library. No paid auth SaaS |
| Secrets | `.env` for dev only; encrypted secrets at rest (e.g. Fernet/AES-GCM with a key from OS keyring or env). OAuth tokens always encrypted |
| Observability | Structured JSON logs, OpenTelemetry (optional), Prometheus + Grafana (optional, local) |
| Packaging | Docker + Docker Compose; also document a non-Docker local install for Windows users |
| Testing | pytest, Playwright (E2E), Vitest/Jest, Testcontainers or Compose-based integration tests |

---

## 5. SYSTEM ARCHITECTURE (components to design separately)

Design each component with: purpose, boundaries, interfaces, data owned, failure modes, scaling path and test strategy.

- **A. Frontend app** (Next.js dashboard)
- **B. Backend API** (FastAPI, REST + WebSocket/SSE for live progress)
- **C. Master Orchestrator** (workflow engine and state machine owner)
- **D. Agent services** (workers running agent logic; agents are logical roles, see Section 7.3)
- **E. Workflow & task queue** (durable, retryable, idempotent jobs)
- **F. Database** (PostgreSQL)
- **G. Media storage** (local, organized per channel/project, with checksums)
- **H. AI Provider Gateway** (single entry point for all LLM/image/TTS/STT calls; enforces quotas, cost limits, license rules, logging, caching)
- **I. YouTube integration service** (OAuth, uploads, metadata, thumbnails, captions, analytics, quota ledger)
- **J. Render engine** (FFmpeg-based, timeline JSON → video)
- **K. Notification service**
- **L. Analytics service**
- **M. Copyright & policy auditing service**
- **N. Security & operational monitoring**

Required diagrams (Mermaid, in `docs/SYSTEM_ARCHITECTURE.md`): context diagram, container diagram, data-flow for one long-form video, data-flow for one Short, OAuth flow, upload flow, failure/retry flow.

---

## 6. FRONTEND (31 sections)

Modern SaaS dashboard: light/dark mode, responsive (desktop, tablet, mobile), sidebar nav, global search, searchable/sortable data tables, charts, media previews, live progress indicators. Every page needs **empty, loading, error and success states** and defined permissions.

Sections: 1 Overview Dashboard · 2 Channel Discovery · 3 Channel Manager · 4 Channel Onboarding · 5 Niche Research · 6 Trend Intelligence · 7 Competitor Research · 8 Channel Branding Studio · 9 Idea Generator · 10 Content Calendar · 11 Script Studio · 12 Storyboard Studio · 13 AI Video Studio (timeline + preview) · 14 Image & Visual Asset Studio · 15 Voiceover Studio · 16 Thumbnail Creator · 17 YouTube SEO Studio · 18 Caption & Subtitle Manager · 19 Render Manager · 20 Upload Manager · 21 Publishing Scheduler · 22 Owner Approval Center · 23 Analytics Dashboard · 24 Growth & Optimization Center · 25 Asset Library (with rights status) · 26 Cost & Usage Manager · 27 Notification Center · 28 AI Agent Control Center · 29 Copyright & Policy Center · 30 Audit & Security Center · 31 Settings & Integrations.

For each page, `docs/FRONTEND_SPECIFICATION.md` must define: route, purpose, layout (desktop + mobile), components, forms and fields (with validation), buttons and actions, tables (columns, filters, sort), API calls, real-time events, permissions per role, and all four states.

**Global UI elements:** Emergency Stop button (always visible), current operating mode badge per channel, quota/usage meter, notification bell, "Private-only mode" banner until the YouTube audit passes.

---

## 7. AI AGENT ARCHITECTURE

### 7.1 Agent list (32)
1 Master YouTube Orchestrator · 2 Niche Discovery · 3 Trend Intelligence · 4 Competitor Research · 5 Keyword Research · 6 Channel Strategy · 7 Channel Branding · 8 Idea Generation · 9 Research · 10 Fact-Checking · 11 Scriptwriting · 12 Storyboard · 13 Visual Creative · 14 AI Image Generation · 15 Voiceover · 16 Video Production · 17 Video Editing · 18 Thumbnail Design · 19 YouTube SEO · 20 Caption & Subtitle · 21 Copyright Auditor · 22 YouTube Policy Auditor · 23 Video Quality Auditor · 24 Upload · 25 Publishing & Scheduling · 26 Analytics · 27 Growth Optimization · 28 Comment Moderation · 29 Notification · 30 Security Auditor · 31 System Auditor · 32 Free-Tier Cost & Usage Monitor.

### 7.2 Specification template (every agent, in `docs/AI_AGENT_ARCHITECTURE.md`)
```
Agent ID / Name / Version
Purpose
Responsibilities
Inputs (typed schema)          Outputs (typed schema, JSON-validated)
Allowed tools                  Disallowed actions
Permissions (read/write scopes on data, YouTube scopes, filesystem paths)
Dependencies (upstream agents / data)
Communication (events consumed / emitted)
Model & provider preference (local first, fallback chain)
Error handling                 Retry rules (max attempts, backoff, idempotency key)
Logging (what is logged, PII redaction)
Performance metrics (latency, success rate, quality score)
Cost & usage limits (tokens/day, calls/day, GPU minutes)
Human approval gates
Testing requirements (unit, golden-output, adversarial)
```
System prompts for every agent go in `docs/AGENT_PROMPTS.md`, versioned, with: role, rules, output JSON schema, refusal conditions, and 1–2 examples.

### 7.3 Implementation guidance
- Treat agents as **logical roles**. Several can share one worker process. Don't create 32 microservices.
- Agents never call each other directly. They read and write through the Orchestrator and the event/task bus, so every step is logged and replayable.
- Agents never call providers directly. All model calls go through the **AI Provider Gateway** (limits, licenses, caching, logging).
- All LLM outputs must be validated against JSON schemas. On invalid output: repair once, then fail the task with a clear reason.
- Auditor agents (21, 22, 23, 30, 31, 32) are **independent**: they cannot be overridden by production agents, only by the owner, and every override is logged.
- Agents may not: publish, change privacy to public, delete YouTube content, enable paid providers, change their own permissions, or disable auditors.

---

## 8. CHANNEL DISCOVERY & NICHE INTELLIGENCE

Research signals (official/permitted sources only): niche opportunity, audience demand, search demand, rising topics, evergreen potential, competitor publishing patterns (via API metadata, not downloads), competition level, advertiser suitability, production difficulty on the owner's hardware, originality opportunity, long-form potential, Shorts potential, and **inauthentic-content risk** (how easy it is to make genuinely original content in this niche).

**Channel Opportunity Score:** a transparent, weighted formula with each criterion's value, weight, evidence links and confidence. The owner can adjust weights. Never state that a niche "will be profitable".

**Channel Blueprint output:** name suggestions (with a reminder to check availability manually), description, brand identity, logo and banner briefs, positioning, target audience, content pillars, video formats, 30-day editorial calendar, 50 initial video ideas, competitor summary, growth strategy, and policy/monetization risks.

**Onboarding:** step-by-step guided manual channel creation (with screenshots/links to official YouTube help), then Google OAuth connection, channel ID verification and a test private upload.

---

## 9. VIDEO PRODUCTION

Two pipelines: **Long-form** and **Shorts** (vertical 9:16, ≤ current Shorts max length, verify).

Every video project contains: research brief · source and fact-verification records · original script (versioned) · opening hook · storyboard · scene descriptions · visual instructions · authorized image/footage assets · voiceover · music/SFX with rights records · timeline JSON · transitions · captions · final render · 3+ thumbnail options · SEO package · QC report · originality/value-add record (what the owner contributed).

Requirements:
- Configurable resolution, aspect ratio, frame rate, duration, audio loudness target (e.g. −14 LUFS integrated, verify current recommendation), codec settings.
- FFmpeg for all editing/rendering. Timeline stored as JSON so renders are reproducible.
- Visual timeline editor + preview in the browser (proxy/low-res preview renders).
- Generative AI video is an **adapter only**. Do not assume free long-form generative video exists. Default visual styles must be achievable locally: motion graphics, kinetic typography, animated diagrams, Ken Burns on original images, data visualizations, owner-recorded footage.
- Owner-voice option: the owner can record their own narration in the Voiceover Studio (strongly recommended for originality).

---

## 10. THUMBNAILS & SEO

**Thumbnails:** prompts, original image generation, text overlays, composition/contrast checks, mobile-size readability check (preview at small sizes), correct dimensions/format/file size (verify current YouTube limits), side-by-side comparison, owner selection and approval. Never copy competitor thumbnails. Never misrepresent video content.

**SEO:** titles (several options, with character counts), descriptions, search terms, tags, chapters (timestamps validated against the final render), hashtags, playlist suggestions, audience settings (made-for-kids decision is **always the owner's**, never auto-set without approval), language and region, **AI disclosure assessment → `containsSyntheticMedia`**, and pre-upload metadata validation. No misleading metadata.

---

## 11. YOUTUBE INTEGRATION

Implement: Google OAuth 2.0 (installed/web app flow with PKCE where applicable) · multiple channel connections · channel identity verification · encrypted token storage · token refresh · revocation and data deletion · **resumable uploads** with resume-after-failure · metadata · custom thumbnails · captions upload · explicit privacy status on every upload · `publishAt` scheduling · processing-status polling · video ID/URL retrieval · Analytics API retrieval · **quota ledger and forecasting** · error classification and recovery · idempotency (no duplicate uploads, enforced by a DB unique key per project + file hash).

Compliance tasks (must be in the roadmap):
- Read and follow the current **YouTube API Services Terms of Service and Developer Policies**; summarize the rules that affect this product in `docs/YOUTUBE_API_INTEGRATION.md`.
- Data retention and deletion rules for API data (check current refresh/deletion requirements for stored API data).
- Prepare the **compliance audit** package (F1) and quota extension request if needed.
- A privacy policy and terms page for the app (needed for the OAuth consent screen).

---

## 12. NOTIFICATIONS

Channels: in-app (default), Telegram (free, recommended), email via SMTP (free), WhatsApp (optional, disabled, cost shown first).

Events: new channel opportunity · trending topic · research complete · script ready · video rendered · thumbnails ready · audit failure · approval needed · upload complete · video published · upload failed · OAuth expired/revoked · API quota near/at limit · usage limit reached · daily and weekly summaries.

Requirements: user preferences per event and channel, quiet hours (owner timezone), delivery tracking, retries with backoff, deduplication keys, and a digest mode to avoid spam.

---

## 13. AUDITING, POLICY & SECURITY

Independent audit modules, each producing a report with: **result, score, failure reason, affected component, responsible agent, evidence and remediation action.**

| Audit | Checks |
|---|---|
| Content | Originality, fact verification, viewer value, repetition across the channel's own catalogue, owner value-add present |
| Copyright | Ownership/license/permission/attribution for every asset; license allows commercial use; no unlicensed music |
| YouTube Policy | Community Guidelines, YPP monetization risks incl. inauthentic/repetitive content, advertiser-friendly guidelines, synthetic-content disclosure, made-for-kids, misleading metadata |
| Video Quality | Resolution, format, audio levels, A/V sync, missing frames, black/frozen frames, silence gaps, subtitle sync, render integrity (ffprobe) |
| Thumbnail | Dimensions, file size, readability at small sizes, misleading presentation |
| AI Agents | Execution logs, permission violations, errors, failed jobs, unusual actions, usage spikes |
| Security | Auth, OAuth, token encryption, access control, data isolation per channel, backups |
| Cost | Free-tier limits, usage, any unexpected charge indicators |

Configurable quality score thresholds, **critical failure conditions that block the workflow automatically**, and owner override with mandatory reason (logged).

---

## 14. OPERATING MODES & SAFETY CONTROLS

- **MANUAL (default):** owner approves research → script → final cut → thumbnail → metadata → upload → publish.
- **SEMI-AUTOMATIC:** agents produce and audit; owner approves publication.
- **FULLY-AUTOMATIC:** only after (a) N successful private test runs (owner-configurable, default 10), (b) the YouTube audit has passed, (c) explicit two-step owner activation per channel. Runs inside owner rules: max videos/day/week per channel, allowed topics, minimum audit scores, quiet hours.

Controls: global **Emergency Stop**, per-agent pause, per-channel switches, **publishing kill switch**, provider kill switch. All are instant, logged, and visible on every page.

---

## 15. DATABASE & BACKEND

Design tables, relationships, indexes, constraints and migrations (Alembic) for: users · roles · permissions · channel profiles · OAuth connections · channel strategies · research sources · trend reports · competitor reports · keywords · video ideas · video projects · scripts + versions · storyboards + scenes · media assets · asset rights/licenses · voice configurations (with consent records) · render jobs · thumbnails · SEO metadata · policy checks · audit reports · approval records · upload jobs · publishing schedules · analytics snapshots · notifications + deliveries · agent configurations · agent runs · workflow tasks · provider registry · usage records · quota ledger · security events · system settings · ADR references.

Backend spec must define: every REST endpoint (method, path, request/response schema, auth, role, errors), WebSocket/SSE events, validation rules, pagination/filter conventions, error format (problem+json), transactions (where and why), idempotency keys, soft vs hard delete, and audit logging for every write.

---

## 16. WORKFLOW STATE MACHINE

Define in `docs/WORKFLOW_STATE_MACHINE.md` (with Mermaid diagrams) the states, transitions, guards, and the agent/owner responsible for each transition, for: Channel (proposed → approved → onboarding → connected → active → paused → disconnected), Idea, Video Project, Render Job, Upload Job, Notification.

Suggested Video Project states:
`IDEA → RESEARCHING → RESEARCH_REVIEW → SCRIPTING → SCRIPT_REVIEW → STORYBOARDING → ASSET_GENERATION → VOICEOVER → ASSEMBLY → RENDERING → QC_AUDIT → (BLOCKED | READY_FOR_APPROVAL) → APPROVED → UPLOADING → PROCESSING → SCHEDULED/PRIVATE → PUBLISHED → ANALYZING → ARCHIVED`, plus `FAILED`, `CANCELLED`, `PAUSED` from any state.

Every transition is persisted, idempotent and resumable after a crash or restart.

---

## 17. TESTING & RELEASE

Automated tests for: frontend (unit + Playwright E2E) · backend APIs (contract tests) · DB migrations (up/down) · agent I/O schemas (golden tests with fixed seeds/mocked models) · workflow execution (full pipeline with mock providers) · media rendering (ffprobe-based assertions on duration, streams, resolution, loudness) · OAuth (mocked + one manual test) · YouTube uploads (mocked API + a **real private upload to a dedicated test channel**) · thumbnail upload · analytics · notifications · audit blocking (prove a failing video cannot be uploaded) · cost limits (prove a provider pauses at its limit) · security (authz, token encryption, secret scanning, dependency audit) · backup and restore.

Environments: `dev` (local), `staging` (local Docker Compose with a test channel, private uploads only), `prod` (owner's machine or optional free-tier host). No paid services required for any environment.

CI: GitHub Actions free tier (verify current free minutes) running lint, type-check, unit and integration tests with mocked providers. GPU/model tests run locally only.

---

## 18. REQUIRED DOCUMENTATION (Phase 0 output)

Create in `docs/`:
```
00_MASTER_PROMPT.md            (this file)
PRODUCT_REQUIREMENTS.md        SYSTEM_ARCHITECTURE.md
TECH_STACK_EVALUATION.md       FRONTEND_SPECIFICATION.md
BACKEND_SPECIFICATION.md       DATABASE_SCHEMA.md
AI_AGENT_ARCHITECTURE.md       AGENT_PROMPTS.md
CHANNEL_DISCOVERY_SPEC.md      VIDEO_PRODUCTION_SPEC.md
THUMBNAIL_SEO_SPEC.md          YOUTUBE_API_INTEGRATION.md
OAUTH_SECURITY.md              WORKFLOW_STATE_MACHINE.md
NOTIFICATION_SPEC.md           AUDIT_AND_POLICY_SPEC.md
FREE_TIER_PROVIDER_MATRIX.md   COST_CONTROL_SPEC.md
DEPLOYMENT_GUIDE.md            TESTING_AND_QA.md
IMPLEMENTATION_ROADMAP.md      CLAUDE_CODE_BUILD_INSTRUCTIONS.md
RISK_REGISTER.md               (new: risks, likelihood, impact, mitigation, owner)
COMPLIANCE_CHECKLIST.md        (new: YouTube ToS, Developer Policies, YPP, Google OAuth, licenses)
GLOSSARY.md                    (new)
adr/ADR-0001-*.md ...          (new: one per key decision)
```
Also create the repo-root **`CLAUDE.md`** (see Section 21).

---

## 19. PHASE 0 — PLANNING EXECUTION ORDER (with owner checkpoints)

**Step 0.1 — Discovery questions.** Ask the owner (in one message):
1. Operating system and hardware (CPU, RAM, GPU model + VRAM, free disk space)?
2. Number of channels planned in the first 6 months, and languages (e.g. English, Urdu, others)?
3. Owner timezone (default Asia/Karachi) and preferred notification channels?
4. Will the owner record their own voice or appear on camera for some content?
5. Any niches already in mind, or niches to avoid?
6. Is a Google Cloud project already created? Is a test YouTube channel available?
7. Comfortable with Docker, or need a non-Docker Windows install?

→ **OWNER CHECKPOINT C0**

**Step 0.2 — PRODUCT_REQUIREMENTS.md** (vision, personas, user stories with acceptance criteria, non-goals, success metrics). → **C1**

**Step 0.3 — Research & TECH_STACK_EVALUATION.md + FREE_TIER_PROVIDER_MATRIX.md + ADRs.** Verify Section 1 facts. → **C2**

**Step 0.4 — SYSTEM_ARCHITECTURE.md, WORKFLOW_STATE_MACHINE.md.** → **C3**

**Step 0.5 — FRONTEND_SPECIFICATION.md, BACKEND_SPECIFICATION.md, DATABASE_SCHEMA.md, OAUTH_SECURITY.md, YOUTUBE_API_INTEGRATION.md.** → **C4**

**Step 0.6 — AI_AGENT_ARCHITECTURE.md, AGENT_PROMPTS.md, CHANNEL_DISCOVERY_SPEC.md, VIDEO_PRODUCTION_SPEC.md, THUMBNAIL_SEO_SPEC.md, NOTIFICATION_SPEC.md, AUDIT_AND_POLICY_SPEC.md, COST_CONTROL_SPEC.md.** → **C5**

**Step 0.7 — IMPLEMENTATION_ROADMAP.md, TESTING_AND_QA.md, DEPLOYMENT_GUIDE.md, CLAUDE_CODE_BUILD_INSTRUCTIONS.md, RISK_REGISTER.md, COMPLIANCE_CHECKLIST.md, CLAUDE.md.** Include a list of unresolved risks, dependencies and limitations. → **C6: SPECIFICATION APPROVAL** (no coding before this).

At each checkpoint, give the owner: a 10-line summary, the decisions made, the open questions, and anything that might cost money or break a policy.

---

## 20. IMPLEMENTATION ROADMAP (build phases)

For **every** phase, `docs/IMPLEMENTATION_ROADMAP.md` must list: goal, exact tasks, dependencies, files to create/modify, acceptance criteria, tests that must pass, a demo script for the owner, and a **free-tier check** ("this phase introduces no paid dependency: ✔").

| Phase | Name | Key outputs / acceptance highlights |
|---|---|---|
| 0 | Research & architecture | All docs approved (C6) |
| 1 | Foundation & repository | Monorepo (`apps/web`, `apps/api`, `workers/`, `packages/shared`, `infra/`), Docker Compose, lint/format/type-check, pre-commit, CI, `.env.example`, health checks. `docker compose up` gives a working "hello" stack |
| 2 | Frontend shell | Layout, navigation, theming, all 31 routes with empty/loading/error states, mocked data, Emergency Stop UI |
| 3 | Backend, DB, auth | Schema + migrations, owner login + 2FA, RBAC, audit log on all writes, API contract tests |
| 4 | Channel onboarding & OAuth | Guided onboarding, OAuth connect/refresh/revoke, encrypted tokens, multi-channel, quota ledger, **first private test upload of a sample file** |
| 5 | Orchestrator & agent infrastructure | State machine, task queue, AI Provider Gateway (Ollama first), provider registry, usage limits, agent run logs, Agent Control Center |
| 6 | Niche discovery & trends | Opportunity score with evidence, blueprint generator, Trend Intelligence from permitted sources |
| 7 | Ideas, research, fact-check, scripts | Idea pipeline, cited research briefs, fact-check reports, versioned scripts, Script Studio |
| 8 | Storyboards, images, voiceover | Storyboards, local image generation, local TTS + owner-recording, rights records for every asset |
| 9 | Editing & rendering | Timeline JSON → FFmpeg render, preview, long-form + Shorts, ffprobe QC tests |
| 10 | Thumbnails & SEO | Thumbnail variants + checks, SEO package, chapters, AI-disclosure assessment |
| 11 | Copyright, policy & quality auditing | All audits, blocking rules, owner override with reason; test proves blocked video cannot upload |
| 12 | Upload & scheduling | Resumable upload, thumbnails, captions, `containsSyntheticMedia`, `publishAt`, idempotency, Private-only mode, audit-application package ready |
| 13 | Analytics & optimization | Analytics snapshots, dashboards, Growth Optimization suggestions (owner-approved only) |
| 14 | Notifications | In-app, Telegram, email, delivery tracking, dedup, digests |
| 15 | Security, testing & deployment | Security review, backup/restore, full E2E with test channel, deployment guide verified on a clean machine |
| 16 | Launch & monitoring | Manual-mode launch on one real channel, monitoring, runbooks, review after 30 days before enabling any automation |

**Rule:** do not start phase N+1 until phase N's acceptance tests pass and the owner says "approved".

---

## 21. `CLAUDE.md` (create at repo root during Step 0.7)

It must contain, at minimum:
- Project summary and the independence rule (no SEMRS OS code or services).
- Repo layout and the command to run each service and each test suite.
- Coding standards (Python: ruff + mypy + pytest; TS: eslint + prettier + tsc strict).
- "Never" list: never add a paid dependency, never hard-code secrets, never call providers outside the Gateway, never set YouTube privacy implicitly, never bypass auditors, never scrape YouTube.
- Definition of Done for a task: code + tests + docs updated + ADR if a decision was made + free-tier check.
- How to work: read the phase in `IMPLEMENTATION_ROADMAP.md`, make a short plan, implement in small commits, run tests, show results, stop.

---

## 22. FINAL DELIVERABLE STANDARD

The documentation must be detailed enough that Claude Code can implement each phase **without guessing missing requirements**. Where something is truly unknown, it must be listed as an open question for the owner, not silently assumed.

Do not reduce this project to a script generator or a simple upload tool. The result is a complete, independent, AI-assisted YouTube media production and channel management platform that is free to run, policy-compliant, auditable and owner-controlled.

**Begin now with Phase 0, Step 0.1. Ask the discovery questions and stop at Checkpoint C0.**
