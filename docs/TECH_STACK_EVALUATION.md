# Technology Stack Evaluation

**Version:** 1.0 (approved at C2, 2026-11-08) · **Date:** 2026-11-08
**Target machine:** H-LITE (Windows 10, 8 GB RAM, no GPU). The design must also scale up to H0–H2 without code changes.
**Rules:** free and open source only · native Windows first · lowest resident RAM wins ties · official APIs only.

Scoring: ★★★ strong · ★★ acceptable · ★ weak · ✖ disqualifying. "RAM" means approximate steady-state resident memory on H-LITE.

---

## 1. Summary of decisions

| Area | Decision | Runner-up | ADR |
|---|---|---|---|
| Install / packaging | **Native Windows install** (PostgreSQL + Python + FFmpeg + a start script). Docker Compose for CI and dev only. | Docker Desktop | ADR-0001 |
| Backend | **Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic** | Django + DRF | ADR-0002 |
| Database | **PostgreSQL 16+** (tests too, no SQLite) | SQLite | ADR-0003 |
| Task queue | **Procrastinate** (PostgreSQL-backed, MIT) | Custom `SKIP LOCKED` queue | ADR-0004 |
| Orchestration | **Custom state machine in PostgreSQL** | LangGraph | ADR-0005 |
| Frontend | **Vite + React + TypeScript + Tailwind + shadcn/ui**, built to static files and served by FastAPI | Next.js | ADR-0006 |
| LLM | **AI Provider Gateway**. Gemini free tier first, Groq free tier second, local Ollama small model as offline fallback | Local-only | ADR-0007 |
| TTS | **Owner voice** (recommended) > **Kokoro-82M** (EN/ES/FR) > **Piper** (DE, UR). Per-voice licence gate. | Gemini TTS free tier | ADR-0008 |
| STT / captions | **faster-whisper** local (int8, `small`) | Groq Whisper free tier | ADR-0009 |
| Visuals | **Non-generative by default** (procedural, charts, kinetic text, owner media, CC0). Generative image adapter disabled until a free provider with a commercial-use licence is verified. | — | ADR-0010 |
| Video engine | **FFmpeg** driven by our own timeline-JSON → filter-graph compiler | MoviePy | ADR-0011 |
| Secrets | **AES-256-GCM** (`cryptography`), master key in **Windows Credential Manager** via `keyring` | Fernet + `.env` key | ADR-0012 |
| Owner auth | **Argon2id** (`argon2-cffi`) + **TOTP** (`pyotp`), HttpOnly session cookies, CSRF tokens | — | ADR-0013 |
| Notifications | **In-app (SSE) + Telegram Bot API**. SMTP optional. WhatsApp disabled. | — | ADR-0014 |
| Research data policy | **Developer-Policy-safe research** (no cross-channel aggregation of YouTube API data) | — | ADR-0015 |
| Publishing safety | **Private by default. `privacyStatus` always explicit.** Private-only mode is optional. | — | ADR-0016 |
| Testing / CI | **pytest, Vitest, Playwright** · **GitHub Actions** (free for public repos) | — | ADR-0017 |
| Repo tooling | **Monorepo. `uv` (Python), `pnpm` (JS). ruff, mypy strict, eslint, prettier, tsc strict, pre-commit, gitleaks** | Poetry / npm | ADR-0018 |

**Estimated idle footprint on H-LITE** (to be measured in Phase 1): PostgreSQL ~150–250 MB + API process ~120 MB + worker process ~150 MB ≈ **0.5 GB**. That is under the NFR-PERF-01 target of 1.5 GB. Heavy jobs run one at a time:

| Heavy job (one at a time) | Approx. RAM |
|---|---|
| Kokoro TTS | ~0.6–1 GB |
| faster-whisper `small` int8 | ~1 GB |
| Ollama 1.5–3B Q4 | ~1.5–2.5 GB |
| FFmpeg 1080p x264 | ~0.3–0.8 GB |

---

## 2. Detailed comparisons

### 2.1 Packaging / install (ADR-0001)

| Criterion | Native Windows install | Docker Desktop (WSL2) |
|---|---|---|
| Free | ★★★ | ★★ (free for personal and small-business use; licence terms apply to larger companies) |
| RAM overhead on 8 GB | ★★★ none | ✖ the WSL2 VM takes about 2 GB or more |
| Owner skill needed | ★★ guided installer script | ★★ |
| Reproducibility | ★★ (pinned versions, `uv` lockfile) | ★★★ |
| CI parity | ★★ (CI runs Linux) | ★★★ |

**Decision:** native install on the owner's PC. Docker Compose is used for CI and for developers on Linux.

### 2.2 Backend framework (ADR-0002)

| Criterion | FastAPI + SQLAlchemy 2 + Alembic | Django + DRF |
|---|---|---|
| Typed contracts (OpenAPI generated from Pydantic) | ★★★ | ★★ (needs drf-spectacular) |
| Async I/O (uploads, SSE, provider calls) | ★★★ native | ★★ partial |
| RAM | ★★★ ~120 MB | ★★ |
| Batteries (admin, auth) | ★★ (we write auth ourselves; scope is small) | ★★★ |
| Licence | MIT / MIT / MIT | BSD |

**Decision:** FastAPI. A typed OpenAPI spec lets us generate the TypeScript client for the frontend (`openapi-typescript`).

### 2.3 Database (ADR-0003)

PostgreSQL wins. It gives us JSONB for timelines and agent I/O, `SKIP LOCKED` for queues, `LISTEN/NOTIFY` for live events, partial unique indexes for idempotency, and a native Windows installer. SQLite was rejected even for tests, because queue and lock semantics differ and tests must run against the real database.

### 2.4 Task queue (ADR-0004)

| Criterion | **Procrastinate** | Celery + Valkey | Dramatiq + Valkey | RQ / Arq |
|---|---|---|---|---|
| Extra server process | ★★★ none (uses Postgres) | ✖ needs a broker | ✖ needs a broker | ✖ Redis-protocol broker |
| Transactional enqueue (job + state change in one DB transaction) | ★★★ | ✖ | ✖ | ✖ |
| Retries, locks, periodic tasks, cancellation | ★★★ | ★★★ | ★★ | ★★ |
| Windows support | 🟡 to verify in a Phase 1 spike (async psycopg on Windows needs `SelectorEventLoop`) | ★★ (Celery dropped official Windows support) | ★★ | ✖ RQ needs `fork` |
| Licence | MIT ✅ | BSD + BSD-3 ✅ | LGPL | BSD / MIT |

**Decision:** Procrastinate. **Fallback:** a ~300-line custom `SELECT … FOR UPDATE SKIP LOCKED` queue behind the same `JobQueue` interface, used if the Windows spike fails. Phase 1 acceptance includes a **Windows CI job** that runs the queue smoke test.

### 2.5 Orchestration (ADR-0005)

| Criterion | **Custom PG state machine** | LangGraph | Temporal |
|---|---|---|---|
| Extra infrastructure | ★★★ none | ★★★ library | ✖ server + DB, about 1 GB+ RAM |
| Durable and resumable after a crash | ★★★ (we persist every transition) | ★★ (checkpointer) | ★★★ |
| Fits our explicit states and owner-approval gates | ★★★ | ★★ (graph-of-LLM-calls model) | ★★ |
| Audit trail per transition | ★★★ native | ★★ | ★★ |
| Complexity | ★★ we own it | ★★ | ★ |

**Decision:** a custom state machine. Transition tables are defined in code, validated by tests and stored in Postgres. Each transition is one DB transaction that also enqueues the next job (transactional outbox via Procrastinate).

### 2.6 Frontend (ADR-0006)

| Criterion | **Vite + React SPA** | Next.js | SvelteKit |
|---|---|---|---|
| Runtime RAM in production | ★★★ 0 (static files served by FastAPI) | ★ Node server ~150–300 MB | ★★ |
| Fits a localhost-only, single-user app | ★★★ (no SSR needed) | ★★ | ★★ |
| Ecosystem (shadcn/ui, TanStack Query/Table, Recharts) | ★★★ | ★★★ | ★★ |
| Licences | MIT | MIT | MIT |

**Decision:** Vite + React 18/19 + TypeScript strict, React Router, TanStack Query and Table, Tailwind, shadcn/ui (MIT; components are copied into the repo) and Recharts. The typed client is generated from OpenAPI.

### 2.7 LLM strategy (ADR-0007)

On H-LITE, local models good enough for scripts in EN/ES/FR/DE/UR do not fit in about 4 GB. So:

1. **Gemini API free tier** (Flash / Flash-Lite family) is the primary provider for research synthesis, scripts and metadata. ⚠️ On the free tier, content is used to improve Google's products. Channels marked **local-only** never use it. Never send secrets or personal data.
2. **Groq free plan** is the secondary provider (open-weight models such as gpt-oss and Qwen) and the automatic fallback when Gemini's daily limit is reached.
3. **Ollama + a ≤ 3B Q4 model** (Apache-2.0 or MIT licence; chosen in Phase 5 after RAM measurement) handles small tasks: classification, JSON repair, offline fallback.
4. All calls go through the **Gateway**, which handles limits, caching, licences, logging and JSON-schema validation.

Rejected: local-only (too weak on 8 GB) and any paid tier (Gemini 4 Argon, etc. are disabled).

### 2.8 Speech (ADR-0008, ADR-0009)

| Language | 1st choice | 2nd choice | Notes |
|---|---|---|---|
| EN | Owner voice | Kokoro-82M (Apache-2.0) | Avoid NC Piper voices (ryan, hfc_female) |
| ES | Owner voice | Kokoro (`e`) / Piper davefx (CC0) | |
| FR | Owner voice | Kokoro (`f`) / Piper siwis (CC-BY 4.0, attribution) | |
| DE | Owner voice | Piper thorsten (CC0) | Kokoro has no German |
| UR | Owner voice | Piper fasih / aegis (MIT per model card; owner verifies) | Highest risk; Gemini TTS free tier is an optional fallback |

STT: **faster-whisper** `small` int8 on CPU (MIT). Captions are aligned to the known script, which is more accurate than free transcription. Urdu captions always need owner review.

### 2.9 Visuals and video (ADR-0010, ADR-0011)

| Option | Verdict |
|---|---|
| Local Stable Diffusion / FLUX on H-LITE | ✖ Out of memory or minutes per image. Some models are non-commercial. |
| Gemini image ("Nano Banana") | ✖ Not free. |
| Procedural graphics (Pillow, Cairo/Skia, matplotlib), kinetic typography, Ken Burns on owner or CC0 photos, data-viz | ✅ **Default.** Fully local and fully licensed. |
| Free-tier cloud image generation | ⏸ Adapter disabled until a provider passes the licence and free-tier check (Phase 8 spike). |
| FFmpeg filter graphs (own compiler) vs MoviePy vs Remotion | **FFmpeg directly.** Lowest RAM and deterministic. MoviePy is slower and RAM-heavy. Remotion needs Node + Chromium and has company-licence terms. |

### 2.10 Security components (ADR-0012, ADR-0013)

- `cryptography` AESGCM, with a 256-bit data key per secret (envelope encryption). The master key is in Windows Credential Manager (`keyring`). Linux CI uses an env-var test key.
- `argon2-cffi` (Argon2id), `pyotp` (TOTP), `itsdangerous` or signed session IDs stored server-side in Postgres. Double-submit CSRF token. Bind to `127.0.0.1`.
- Models load from safetensors or ONNX only, with SHA-256 pinned in the registry.
- Supply chain: `uv.lock` and `pnpm-lock.yaml`; `pip-audit`, `pnpm audit`, `gitleaks` in pre-commit and CI.

### 2.11 Notifications (ADR-0014)

In-app notifications use SSE from FastAPI (no WebSocket server needed). Telegram Bot API (free; owner creates a bot via BotFather, token stored encrypted). SMTP is optional. WhatsApp is a disabled Tier-P adapter.

### 2.12 Testing (ADR-0017)

pytest + pytest-asyncio + httpx (API contract tests against the OpenAPI schema), and real Postgres via a CI service container or a local install. Vitest + Testing Library for the frontend. Playwright for E2E (CI runs Chromium). ffprobe-based assertions for renders. GitHub Actions on Linux and Windows runners, free for this **public** repo.

---

## 3. Hardware scaling path (same code, different config)

| Profile | Changes (config only) |
|---|---|
| H-LITE (now) | Cloud free-tier LLM, Kokoro/Piper, procedural visuals, 1 heavy job at a time, renders at night |
| H0 (16 GB) | Local 7B Q4 LLM becomes viable as a secondary option; 2 parallel light jobs |
| H1 (8 GB VRAM) | Local LLM first; local image adapter (licence-gated SD-class model) enabled; GPU whisper |
| H2 (12–24 GB) | Larger local models; faster renders (NVENC) |
