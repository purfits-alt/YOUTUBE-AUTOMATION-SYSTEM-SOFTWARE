# TubeForge — Project Progress

> Living document. Updated at every checkpoint and at the end of every phase.

**Current phase:** Phase 6 — Niche discovery & trends
**Current step:** P6-A built (research fetcher, sources, Wikipedia pageviews, RSS); next P6-B (discovery agents and scoring). Phase 5 approved 2026-11-10 (PR #9 merged). The owner's manual real-OAuth test (Phase 4) is still open; it will use the owner's new channel.
**Last updated:** 2026-11-10

---

## Checkpoint log

| Checkpoint | Scope | Status | Date | Owner decision |
|---|---|---|---|---|
| C0 | Discovery questions | ✅ Closed | 2026-11-08 | Answers + defaults recorded below |
| C1 | PRODUCT_REQUIREMENTS.md | ✅ Approved | 2026-11-08 | All proposed defaults OQ-1…OQ-6 accepted |
| C2 | Tech stack, provider matrix, ADRs, fact verification | ✅ Approved | 2026-11-08 | All 18 ADRs accepted + owner added: own-voice cloning (ADR-0019) and optional stock media incl. paid (ADR-0020) |
| C3 | System architecture, state machine | ✅ Approved | 2026-11-08 | Defaults A-1…A-3 accepted; install root `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE` |
| C4 | Frontend, backend, DB, OAuth, YouTube API specs | ✅ Approved | 2026-11-08 | Defaults: TOTP optional (recommended), backup 03:00 PKT, digests daily 09:00 / weekly Mon 09:00, no external editors enabled yet |
| C5 | Agents, prompts, discovery, production, SEO, notifications, audit, cost specs | ✅ Approved | 2026-11-08 | Defaults accepted (2 long + 4 Shorts/week start, originality ≥ 70, provider limits entered in Phase 5, 07:00/06:00/03:00 PKT jobs) + owner added script craft: packaging promise in intro, 10–15 s hook, mid-video re-hooks, honest curiosity/suspense, human voice (US-4.5) |
| C6 | Roadmap, QA, deployment, build instructions, risks, compliance, CLAUDE.md — **SPEC APPROVAL** | ✅ Approved | 2026-11-08 | Full specification approved. Owner asked for a completeness re-check → TRACEABILITY_MATRIX.md added; stale glossary/version items fixed. Defaults: merge planning to `main` via PR; one branch per build phase. |

---

## Phase 0 task list (Step 3 — actionable plan)

| ID | Task | Depends on | Output | Acceptance criteria |
|---|---|---|---|---|
| P0-01 | Inspect repo and planning docs; create repo skeleton | — | `docs/`, git repo | ✅ Done. Master prompt saved; repo initialised |
| P0-02 | Validation of the brief | P0-01 | `PHASE0_VALIDATION_REPORT.md` | ✅ Done (draft). Conflicts, gaps, limits, risks listed |
| P0-03 | Discovery questions (Step 0.1) | P0-01 | Owner answers | ✅ Done. Answers/defaults recorded |
| P0-04 | Product requirements (Step 0.2) | P0-03 | `PRODUCT_REQUIREMENTS.md`, `GLOSSARY.md` | ✅ Approved at C1. Personas, user stories with testable acceptance criteria for all 25 workflow steps, non-goals, success metrics (no revenue promises). Owner approves at C1 |
| P0-05 | Verify platform facts F1–F9 from official sources | P0-03 | Records in `FREE_TIER_PROVIDER_MATRIX.md`, `YOUTUBE_API_INTEGRATION.md` | ✅ Done (F7 not needed — adapter disabled). Each fact has URL + verification date, or is marked `UNVERIFIED` with a design workaround |
| P0-06 | Tech-stack evaluation + ADRs (Step 0.3) | P0-03, P0-05 | `TECH_STACK_EVALUATION.md`, `adr/ADR-0001…` | ✅ Approved at C2 (20 ADRs). ≥2 options per area of Section 4, compared on free status, licence, OS support, hardware, maintenance, testability. One ADR per decision. Owner approves at C2 |
| P0-07 | System architecture + state machine (Step 0.4) | P0-06 | `SYSTEM_ARCHITECTURE.md`, `WORKFLOW_STATE_MACHINE.md` | ✅ Approved at C3 (16 Mermaid diagrams, all parse-checked). 7 required Mermaid diagrams. Components A–N with interfaces and failure modes. All 6 state machines with guards and owners. Owner approves at C3 |
| P0-08 | Interface specs (Step 0.5) | P0-07 | Frontend, backend, DB, OAuth security, YouTube API docs | ✅ Approved at C4. All 31 pages fully specified (4 states each). Every endpoint typed. Every table with constraints and indexes. Owner approves at C4 |
| P0-09 | Domain specs (Step 0.6) | P0-07 | Agent architecture, prompts, discovery, production, SEO, notifications, audit, cost docs | ✅ Approved at C5. All 32 agents follow the template in §7.2. Prompts versioned with JSON schemas. Audit blocking rules defined. Owner approves at C5 |
| P0-10 | Roadmap + ops docs (Step 0.7) | P0-08, P0-09 | Roadmap, testing, deployment, build instructions, risk register, compliance checklist, `CLAUDE.md` | ✅ Approved at C6. Each build phase lists tasks, files, acceptance tests, demo script and free-tier check ✔. **C6 spec approval** |

### Build-phase dependency outline (preliminary; finalised in P0-10)

```
P1 Foundation ─┬─ P2 Frontend shell
               └─ P3 Backend/DB/Auth ── P4 OAuth + quota ledger (+ test-only upload)
                                     └─ P5 Orchestrator + Gateway ─┬─ P6 Niche/Trends
                                                                   ├─ P7 Ideas/Research/Scripts ── P8 Storyboard/Images/Voice ── P9 Render
                                                                   │                                                           └─ P10 Thumbs/SEO
                                                                   └──────────────────────────────── P11 Auditing (gates P12)
                                                                       P12 Upload/Schedule ── P13 Analytics/Optimisation (+ comment moderation)
                                                                       P14 Notifications ── P15 Security/E2E/Deploy ── P16 Launch
```

---

## C0 answers (closed 2026-11-08 — owner said "use defaults" for open items)

| Q | Answer | Source |
|---|---|---|
| 1 Hardware | Windows 10, 8 GB RAM, no GPU → **H-LITE** profile (validation report §10). Free disk: unknown → installer checks for ≥ 60 GB and warns | Owner / default |
| 2 Channels / languages | Languages supported: EN, ES, FR, DE, UR. **Launch: 1 channel, English.** Others added after launch review | Owner / default |
| 3 Timezone / notifications | Asia/Karachi. **In-app + Telegram** (email optional, off) | Owner / default |
| 4 Own voice / camera | Unknown → owner-voice recording supported and **recommended**; TTS allowed with value-add checks | Default |
| 5 Niches | None preset → Phase 6 discovery runs open, owner picks | Default |
| 6 Google Cloud / test channel | Not yet → setup guide in DEPLOYMENT_GUIDE, needed before Phase 4 | Default |
| 7 Docker | **Native Windows install primary**; Docker for CI/dev only | Default |
| 8 GitHub repo | `purfits-alt/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE` (**public**) | Owner |
| 9 Dashboard access | **Localhost only** (`127.0.0.1`) | Default |
| 10 Policy identity / revenue scope | Identity: individual owner, name & email filled in before Phase 4. **No monetary analytics scope** for now | Default |
| D-10 Windows 10 EOL | **Accept risk** with mitigations: localhost-only, encrypted token store, OS-keyring key, updated browser/AV; recorded in RISK_REGISTER | Default |

## Open decisions (beyond C0 questions)

| ID | Decision | Decide at |
|---|---|---|
| D-1 | Task queue — **decided: Procrastinate (ADR-0004)** | ✅ C2 |
| D-2 | Orchestration — **decided: custom PG state machine (ADR-0005)** | ✅ C2 |
| D-3 | Frontend — **decided: Vite + React SPA (ADR-0006)** | ✅ C2 |
| D-4 | Visuals — **decided: non-generative default, image adapter disabled (ADR-0010)** | ✅ C2 |
| D-5 | TTS — **decided: owner voice > Kokoro > Piper (ADR-0008)** | ✅ C2 |
| D-6 | Privacy-policy hosting — **proposed: GitHub Pages of this public repo (free); domain verification only needed if consent screen goes "In production" with sensitive scopes — detailed in Step 0.5** | C2/C4 |
| D-7 | Dashboard network exposure — **decided: localhost only** | ✅ C0 |
| D-8 | Monetary Analytics scope — **decided: not now** | ✅ C0 |
| D-9 | Media retention & backup — **decided: 30-day intermediates, daily DB+secrets backup** | ✅ C1 |
| D-10 | Windows 10 EOL — **decided: accept risk with mitigations**; update: enrol in free consumer ESU (to Oct 2027) | ✅ C0 / C2 |
| D-11 | Research data policy under YouTube Data Aggregation rule — **decided: conservative (ADR-0015)** | ✅ C2 |
| D-12 | Publishing safety after F1 reversal — **decided: explicit privacy, private by default (ADR-0016)** | ✅ C2 |
| D-13 | Owner voice cloning — **decided: OpenVoice V2 converter (default) + Chatterbox zero-shot (optional), owner-only with consent (ADR-0019)** | ✅ C2 |
| D-15 | Install location — **decided: `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE`** (all program/data/DB/models on D:) | ✅ C3 |
| D-14 | Stock media — **decided: manual import always; Pexels/Pixabay optional; paid APIs disabled, budget 0 (ADR-0020)** | ✅ C2 |
| D-16 | Optional external editors (Canva, CapCut, InShot, Filmora, any other) — **decided: built-in default + optional hand-off/re-import picker (ADR-0021)** | ✅ owner request, Step 0.5 |

---

## Phase 0 summary (for C6)
- 26 planning documents in `docs/` + 21 ADRs + root `CLAUDE.md`. All 19 Mermaid diagrams parse-checked.
- Owner additions incorporated: own-voice recording/cloning (ADR-0019), optional stock media incl. paid (ADR-0020), optional external editors (ADR-0021), install root on D:, script craft (US-4.5).
- Unresolved items, dependencies and limitations: see `RISK_REGISTER.md` → "Unresolved items carried into build".

## Phase reports

### Phase 1 — Foundation & repository · report 2026-11-08 · branch `phase-1-foundation` · ✅ accepted 2026-11-08 (PR #4 merged; owner: "go ahead")

**Plan (from IMPLEMENTATION_ROADMAP Phase 1):** monorepo, uv + FastAPI health/readiness, Vite+React placeholder, PostgreSQL + Alembic + Procrastinate (with Windows spike), light/heavy workers, tooling and CI (Linux + Windows path with spaces), `tubeforge.ps1`, RAM measurement.

1. **Modules implemented**
   - `tubeforge.config`: settings from env → TOML → defaults. **Loopback-only host enforced.** Windows default home `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE`.
   - `tubeforge.logging`: structlog JSON with secret redaction (keys + Google/Groq/Telegram/Bearer/DSN-password patterns).
   - `tubeforge.main`: `/healthz`, `/readyz` (DB, queue schema, data dir) as problem+json; Host-header guard (DNS-rebinding defence); serves the built SPA or a placeholder.
   - `tubeforge.db.session`, `tubeforge.queue`: Procrastinate behind a `JobQueue` interface; queues per SYSTEM_ARCHITECTURE §4-E; light (4) and heavy (1) profiles.
   - `tubeforge_workers`: worker CLI (`--queues light|heavy`, `--once`) and smoke tasks.
   - `apps/web`: React 19 + Vite 8 + TS strict placeholder showing backend status.
   - `tools/check_traceability.py`, `tools/check_licenses.py`.
   - `infra/windows/tubeforge.ps1` (doctor / setup / start / stop / status, PowerShell 5.1) and `get-tubeforge.ps1` (download to D:).
2. **Files created/modified:**
   - `pyproject.toml`, `uv.lock`, `apps/api/{alembic.ini, migrations/*, tubeforge/*}`, `workers/tubeforge_workers/*`
   - `apps/web/*` (package.json, pnpm-lock.yaml, src, tests/e2e, configs), `packages/shared/enums.json`
   - `tools/*`, `tests/{conftest.py, unit/*, integration/*}`, `infra/windows/*`, `infra/compose/*`
   - `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `.gitignore`, `.env.example`, `site/index.html`
   - Updated: `CLAUDE.md` (verified commands), `README.md` (Windows/D: quick start), ADR-0004 (spike result).
3. **Database changes:** Alembic revision `0001` = Procrastinate queue schema (upgrade and downgrade, both tested). No application tables yet (Phase 3).
4. **APIs implemented:** `GET /healthz`, `GET /readyz`, `GET /` (dashboard), `GET /api/docs` and `/api/openapi.json` (dev only; hidden in prod).
5. **Agents created:** none (Phase 5+). Smoke tasks `tf:mnt.ping` (light) and `tf:heavy.ping` (heavy) prove both worker profiles.
6. **Tests executed (Linux, this session):**

   | Suite | Result |
   |---|---|
   | Python (unit + integration, real PostgreSQL 16) | **43 passed** |
   | ruff lint + format | pass |
   | mypy --strict | pass (12 files) |
   | Web: vitest | **2 passed** |
   | Web: eslint + prettier | pass |
   | Web: tsc strict | pass |
   | Web: build | pass (220 kB JS, 69 kB gzipped) |
   | Playwright e2e (desktop + mobile, real API + DB + built web) | **4 passed** |
   | Traceability check | pass |
   | pip-audit | 0 known vulnerabilities |
   | pnpm audit | 0 (a moderate dev-only `minimatch` advisory was fixed via a pnpm override to 11.0.1) |
   | Licence gate (Python + web) | pass |

   The licence-gate test caught a real gap ("GNU Affero …" was not matched) and it was fixed.
   **Not run here:** gitleaks (running an external binary was not permitted in this session; it runs in CI) and the Windows CI job (runs on GitHub after push; see the Actions tab).
7. **Free-tier services used:** none at runtime. Tooling: PostgreSQL, Python/uv, Node/pnpm, Procrastinate (MIT), GitHub Actions (free for public repo). **This phase introduces no paid dependency: ✔**
8. **Resource consumption (idle, Linux container):** API ≈ 94 MB · light worker ≈ 54 MB · heavy worker ≈ 54 MB · PostgreSQL (all backends) ≈ 350 MB RSS (shared memory counted per process, so this overstates it) → **≈ 550 MB total**. Target ≤ 1.5 GB ✔. Owner's Windows PC (2026-11-08): the first `status` showed 4 MB per process because it measured only the `.venv\Scripts` launcher, not its Python child; fixed (now sums the process tree and prints a total). **Windows (owner PC, idle, after fix): API 97 MB · light worker 67 MB · heavy worker 67 MB → 231 MB for TubeForge** (PostgreSQL not included; even with the Linux PostgreSQL figure the total stays well under 1.5 GB ✔).
9. **Known limitations:**
   - **Owner demo, 2026-11-08 (Windows 10 Pro 19045, 7.9 GB RAM, PS 5.1):** `doctor` → PostgreSQL 16 installed (data on D:) → `setup` → `start` (api + both workers, readiness `ready`) → dashboard placeholder opened at http://127.0.0.1:8765 → `stop`. ✔
   - Fixes from the owner run (branch `claude/vigilant-tesla-lkhgme`): README execution-policy/Unblock-File step; uv cache moved to `app\.cache\uv` (hardlink warning); `setup` now verifies the postgres password (psql `-w`, 3 attempts, exit codes checked, pgpass written only on success; previously a failed login could leave a pgpass entry for a role that didn't exist); `status`/`stop` cover the launcher's child processes. These script changes still need the Windows CI job or an owner re-run to confirm.
   - The hidden password prompt is awkward to use (no echo, paste unreliable). Workaround used: `setup -NonInteractive` with `TUBEFORGE_PG_SUPERUSER_PASSWORD`. Better UX deferred to Phase 15 installer.
   - `setup` does not yet install PostgreSQL, Python or FFmpeg automatically. It checks for them and prints install hints (automated installers: Phase 15).
   - The idempotency key currently maps to Procrastinate's queueing lock (blocks duplicate *waiting* jobs). Durable exactly-once via `job_meta` comes in Phase 5.
   - Opening a PR from this session is blocked (GitHub CLI not authorised). Pushing works.
   - ~~No LICENSE file~~ resolved 2026-11-08: owner chose **MIT** (ADR-0022, `LICENSE`).
10. **Remaining tasks for Phase 1 acceptance:**
    - ~~Windows CI job green~~ ✔ (PR #4). The web job's post-step `uv cache prune` timed out because the e2e API ran under `uv run`; fixed in CI after the merge.
    - ~~Owner runs the demo on their PC~~ done 2026-11-08 ✔.
    - ~~Record the Windows memory figure~~ done: 231 MB (fixed `status` confirmed working on Windows) ✔.

**Demo script (owner):** see README "Get it onto your PC" → `tubeforge.ps1 doctor` → (install PostgreSQL 16 if missing) → `tubeforge.ps1 setup` → `tubeforge.ps1 start` → browser shows "TubeForge is running · Backend: ok" → `tubeforge.ps1 status` → `tubeforge.ps1 stop`.

**Open questions for the owner:** (1) ~~Licence~~ MIT, decided 2026-11-08 (ADR-0022). (2) Remote Control folder sharing for D: (lets Claude work directly on the PC).


### Phase 2 — Frontend shell · report 2026-11-08 · branch `claude/vigilant-tesla-lkhgme` · merged to `main` (PR #5) · ✅ approved by the owner 2026-11-08

**Plan (IMPLEMENTATION_ROADMAP Phase 2, FRONTEND_SPECIFICATION §0–§32):**
1. Shell: grouped sidebar (desktop), icon rail (tablet), bottom tab bar + drawer (mobile); top bar; light/dark/system theme via CSS tokens; `i18n/en.json`.
2. Global elements (mocked): Emergency Stop (confirm + reason; clearing needs re-auth), channel switcher with mode badge and Private-only badge, quota/usage meter, notification bell, `Ctrl+K` search, global banners.
3. All 31 routes from a single page registry; data comes through the API client from **MSW** mock handlers. A dev scenario switcher forces empty / loading / error / success on any page.
4. Shared components: DataTable (TanStack Table), StatTile, StateCard, ProblemDisplay (problem+json), ConfirmDialog, ReauthModal, Toasts, SSE client stub.
5. OpenAPI pipeline: stub spec in `packages/shared/openapi.stub.json` → `openapi-typescript` → typed `openapi-fetch` client; CI fails if the generated file is stale. Replaced by the FastAPI spec in Phase 3.
6. Tests: Vitest component tests; Playwright 31 routes × 4 states (124), axe per route (0 serious/critical), mobile 390×844 for pages 1/22/27, visual snapshots of key pages.

Page-specific editors, forms and charts (e.g. weight sliders, script editor, analytics charts) arrive with their feature phases; Phase 2 gives each page its layout frame, mocked table/tiles and actions.

**Owner additions during the phase:** "a premium dashboard", "icons, animation and Lottie" → ADR-0023 (own design tokens, inline icons, SVG charts, CSS motion, our own Lottie animations; all respect "reduce motion").

1. **Modules implemented**
   - Shell (`apps/web/src/app`, `components/Navigation.tsx`, `TopBar.tsx`, `Banners.tsx`): dark "studio" sidebar with logo and group icons (≥1024 px), icon rail (640–1023 px), bottom tab bar + drawer (<640 px); top bar with Emergency Stop, `Ctrl+K` search, channel switcher with mode and Private-only badges, quota meter, notification bell, theme (light/dark/system).
   - Global elements (mock): Emergency Stop (2 clicks, optional reason, pulsing when active; clearing asks for the password via step-up), banners (Emergency Stop, kill switch, Private-only, token expiring, backend offline).
   - 31 routes from one registry (`pages/registry.ts`), texts in `i18n/en.json`. Pages 2–31 share `PageView` (hero, actions, KPI tiles, sortable table, four states); page 1 Overview has its own layout (live Lottie orb, KPI tiles with count-up + sparklines, 14-day views chart, quota rings, pipeline funnel, approvals, alerts, schedule, activity). Project pages 11–18 show the Project header (state stepper, blocking guards).
   - Shared components: DataTable (TanStack Table), StatTile, StateCard (with Lottie), ProblemDisplay (problem+json, code + request id), Dialog/ConfirmDialog (native `<dialog>`), ReauthModal (react-hook-form + zod; retries the request after step-up), Toasts (ARIA live), SSE event-bus stub, icons, charts, Lottie player (lazy).
   - Mock backend: MSW handlers (`mocks/`) for all page endpoints, `/shell`, Emergency Stop, step-up and search. Scenario switcher (`?scenario=` or dev toolbar) forces empty/loading/error/success.
   - OpenAPI pipeline: `packages/shared/openapi.stub.json` → `openapi-typescript` → typed `openapi-fetch` client; `api:check` in CI fails on drift.
   - API: deep links (`/approvals`, `/projects/p-101/script`, …) now serve the SPA; API paths and missing files stay 404.
   - `tools/gen_lottie.py`: generates the three Lottie animations (original artwork).
2. **Files created/modified:** `apps/web/{src/**, tests/e2e/*, public/mockServiceWorker.js, package.json, pnpm-lock.yaml, vite.config.ts, tsconfig.json, playwright.config.ts, .prettierignore}`, `packages/shared/openapi.stub.json`, `apps/api/tubeforge/main.py`, `tests/unit/test_api_system.py`, `tools/gen_lottie.py`, `.github/workflows/ci.yml`, `CLAUDE.md`, ADR-0023 (+ ADR-0006 amended, ADR index), `FRONTEND_SPECIFICATION.md` stack line.
3. **Database changes:** none.
4. **APIs implemented:** none real (mocked in the browser). Backend change: SPA deep-link fallback.
5. **Agents created:** none.
6. **Tests executed (Linux, this session):**

   | Suite | Result |
   |---|---|
   | Vitest (registry, app shell incl. Emergency Stop + step-up, search, states, DataTable, tones) | **17 passed** |
   | Playwright routes × states (31 × 4) | **124 passed** |
   | axe WCAG 2.2 AA, 31 routes × light/dark | **62 passed** (0 serious/critical) |
   | Mobile 390×844 (pages 1, 22, 27 + tab bar/drawer) | **4 passed** |
   | Shell (Emergency Stop flow, theme, Ctrl+K, scenario switcher, all 31 sidebar links), smoke | **9 passed** |
   | Visual snapshots (4 key pages × light/dark) | **8 passed** |
   | Python unit (incl. new SPA fallback test), ruff, mypy --strict, traceability | pass |
   | eslint + prettier, tsc strict, `api:check`, build | pass |
   | Web licence gate (prod deps), pnpm audit (high) | pass / 0 vulnerabilities |

   Two axe findings were real and fixed: low contrast of the page number on the active menu item, and the scrollable KPI row not being keyboard-focusable. Axe and visual tests run with reduced motion, so they measure the final page and not a card halfway through its fade-in.
   **Not run here:** Python integration tests (need PostgreSQL; they run in CI).
7. **Free-tier services used:** none. New dependencies, all free: react-router, TanStack Query/Table, msw, openapi-fetch/openapi-typescript, react-hook-form, zod, Tailwind, lottie-web (MIT), Inter font (OFL-1.1), axe-core/playwright (MPL-2.0, dev only). **This phase introduces no paid dependency: ✔**
8. **Resource consumption:** build JS ≈ 585 kB (180 kB gzip) main + 437 kB MSW (Phase 2 only) + 169 kB Lottie player (lazy, 47 kB gzip). No new server processes.
9. **Known limitations:**
   - All data is mocked; buttons show a "queued (mock)" toast. Real data, auth and permissions arrive in Phase 3.
   - Page-specific editors, forms and charts (script editor, weight sliders, timeline, analytics charts) arrive with their feature phases; Phase 2 gives each page its frame, KPIs, table and actions.
   - The step-up mock accepts any password except "wrong".
   - Visual snapshots: the first baselines (rendered in this session) differed from GitHub's runner by ~2 % of pixels (font anti-aliasing), so baselines are now rendered by CI itself: a commit message containing `[update-snapshots]` makes the web job run the full suite, rewrite the screenshots and commit only that folder.
   - **Fixed after the first CI run (Windows job):** `status`/`stop` walked process trees by parent ID only; with Windows PID reuse, unrelated processes were counted (3.4 GB) and `stop` killed the CI shell. Now a child must start after its parent and be one of TubeForge's own executables, and a stale pid file pointing at another program is ignored. CI now fails if the memory total is implausible or a TubeForge process survives `stop`.
10. **Remaining tasks for Phase 2 acceptance:** ~~CI green on the PR~~ ✔ (PR #5 green on all four jobs, merged 2026-11-08); owner demo below; owner replies "approved".

**Demo script (owner):** `git pull` in `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app` → install Node.js 22 LTS from nodejs.org and then `npm install -g pnpm@10.28.0` (one time, free) → `tubeforge.ps1 setup` (now builds the dashboard) → `tubeforge.ps1 start` → open http://127.0.0.1:8765 → click through every sidebar item → use "Scenario (dev)" bottom-right to show empty / loading / error → press Emergency Stop (add a reason) → clear it (any password) → `Ctrl+K` and search "thumb" → switch Theme to Dark → make the window phone-sized.

### Phase 3 — Backend, database & auth · report 2026-11-08 · branch `claude/vigilant-tesla-lkhgme` · ✅ approved by the owner 2026-11-08

**Plan (IMPLEMENTATION_ROADMAP Phase 3):** full schema + migrations; repository with channel scoping, optimistic locking, soft delete; owner auth with 2FA, sessions, CSRF, Host/Origin checks, lockout, step-up; RBAC on every route; audit log hash chain + security events; secrets (AES-GCM, Credential Manager); controls & settings API; problem+json, idempotency, cursor pagination, SSE; wire the dashboard to the real API with a generated client and a committed OpenAPI snapshot; contract tests.

1. **Modules implemented**
   - **Schema:** `tools/gen_schema_sql.py` generates the DDL for all **80 tables** from DATABASE_SCHEMA.md (ADR-0024): enum CHECKs from `enums.json`, FKs after all tables, `updated_at` triggers, append-only triggers on (AO) tables. Migrations 0002 (schema) and 0003 (41 permissions, 4 roles, settings row). `upgrade head` / `downgrade base` both work.
   - **Repository** (`db/repository.py`): explicit `ChannelScope` on every scoped query (out of scope = 404), `update_versioned` (optimistic locking), soft delete. Typed ORM models for the tables Phase 3 uses.
   - **Secrets** (`secrets/`): AES-256-GCM, HKDF per-purpose keys, AAD `table:column:row_id`; master key in Windows Credential Manager (`keyring`), test-only env key refused in prod on Windows.
   - **Auth** (`api/v1/auth.py`, `auth/`): Argon2id; lockout (5 failures / 15 min → 423); signed session cookie (HMAC, HttpOnly, SameSite=Strict, idle 8 h / absolute 7 d, rotated on login and MFA); double-submit CSRF; Origin check; TOTP enrol/confirm/verify/disable with QR and 10 one-time recovery codes; 5-minute step-up (`/auth/reauth`); password change (≥ 12 chars + zxcvbn ≥ 3, other sessions revoked); sessions list/revoke.
   - **RBAC** (`api/deps.py`): `require("perm")` on routes; denial → 403 + `PERMISSION_DENIED` event. A test walks every `/api/v1` route and fails if one has no rule; only login is public.
   - **Audit** (`audit/`): SHA-256 hash chain under an advisory lock; `/audit-log` (cursor pages), `/audit-log/verify-chain`, `/security-events`. Every write route writes exactly one row.
   - **Controls & settings** (`api/v1/system.py`): Emergency Stop (press: `emergency.activate`; clear: `emergency.clear` + step-up), publishing kill switch, kill switches; settings with ETag / If-Match (428 / 412). Recorded and broadcast now; enforced by the orchestrator/workers from Phase 5.
   - **Cross-cutting:** problem+json everywhere (documented on every route), Idempotency-Key (replay / 422 mismatch, 24 h), cursor pagination, SSE `/events/stream` with Last-Event-ID replay.
   - **Admin CLI:** `tubeforge-admin init-keys | create-owner | has-owner | reset-password`. `tubeforge.ps1 setup` now creates the master key and asks for the owner account; new `tubeforge.ps1 reset-password`.
   - **Web:** sign-in and 2FA screens; real Emergency Stop (Idempotency-Key, password re-entry to clear), live updates over SSE (other tabs see Emergency Stop at once), account menu with Sign out; **Settings** (general settings, 2FA with QR + recovery codes, password, sessions) and **Audit & Security Center** (audit log, verify chain, security events) use the real API. Other pages keep mock data until their phases.
   - **Contract:** `packages/shared/openapi.json` (committed, test fails if stale) → generated TS client; schemathesis property tests on every GET endpoint.
2. **Files created/modified:** `apps/api/tubeforge/{admin.py, api/*, audit/, auth/, events/, secrets/, db/{ids.py, models/, repository.py, schema_v1.sql}, main.py}`, `apps/api/migrations/versions/0002_*, 0003_*`, `tools/{gen_schema_sql.py, export_openapi.py}`, `packages/shared/{openapi.json, openapi.stub.json}`, `apps/web/src/{app/AuthGate.tsx, pages/{SecurityPage,SettingsPage}.tsx, components/UserMenu.tsx, lib/{api/client.ts, useBackend.ts, sse.ts}, mocks/testApi.ts}`, e2e (`global-setup.ts`, `stateful.spec.ts`), `infra/windows/tubeforge.ps1`, CI, docs (DATABASE_SCHEMA, DEPLOYMENT_GUIDE, FRONTEND/ADR index, CLAUDE.md, ADR-0024).
3. **Database changes:** migrations 0002 + 0003. Schema document additions (fixed in the document first): `idempotency_keys`, `user_recovery_codes`, `sessions.reauth_at` — the API/security specs required them but the approved schema had no place for them.
4. **APIs implemented:** 22 under `/api/v1` (auth ×11, controls/settings ×8, audit/security ×3) + `/events/stream`; `/readyz` now also checks the master key.
5. **Agents created:** none (Phase 5).
6. **Tests executed (Linux, this session):**

   | Suite | Result |
   |---|---|
   | Python unit + integration (real PostgreSQL 16) | **88 passed** |
   | Contract (schemathesis: every GET endpoint, generated cases; status codes, content types, schemas, Allow, positive-data acceptance) | **pass (25 groups)** |
   | Vitest (incl. sign-in, sign-out, settings If-Match, security, Emergency Stop + re-auth) | **22 passed** |
   | Playwright: routes × states (124), axe light/dark (62), mobile (4), shell/smoke (7) | **198 passed** |
   | Playwright stateful (Emergency Stop live across tabs + re-auth, audit page, sign-in/out + axe) | **3 passed** |
   | Visual snapshots | to be re-rendered by CI (`[update-snapshots]`): the top bar gained Sign out |
   | ruff, mypy --strict, eslint, prettier, tsc, `api:check`, OpenAPI snapshot, schema-SQL sync, traceability | pass |
   | gitleaks (tree + branch commits), pip-audit, pnpm audit, licence gate | clean |

   Real defects the tests found and fixed this phase: non-IP client addresses broke `inet` columns; sign-out left the app open; the app did not render when service workers are blocked; the contract documented `application/json` errors instead of problem+json, dropped the 405 `Allow` header for multi-method paths, used a regex that differs between Python and JSON Schema, and documented times as JSON-Schema `time` (needs an offset) — settings times are now `HH:MM`; cursors now have a documented pattern.
7. **Free-tier services used:** none. New dependencies (all free): argon2-cffi, pyotp, cryptography (≥ 50.0.2: four advisories fixed in 48–50), keyring, segno, zxcvbn; dev: schemathesis. **This phase introduces no paid dependency: ✔**
8. **Resource consumption:** unchanged process count; Argon2 uses 64 MiB for ≈ 0.1–0.3 s per sign-in.
9. **Known limitations:**
   - Emergency Stop / kill switches are recorded, audited and broadcast, but nothing runs yet to stop (enforcement in Phase 5).
   - SSE uses an in-process buffer (API process only); worker events join via PostgreSQL LISTEN/NOTIFY in Phase 5.
   - Separate auditor / read-only DB roles arrive with the auditors (Phase 11); append-only tables are protected by triggers.
   - Expired `idempotency_keys` are skipped on read; the cleanup job comes with the maintenance queue (Phase 5).
   - General rate limiting (600/min) is not implemented yet (login is protected by the lockout); planned for Phase 15.
   - Only the OWNER role is used; channel-scoped roles are modelled and tested but no UI to invite users (out of scope v1).
10. **Remaining tasks for Phase 3 acceptance:** CI green (incl. Windows `init-keys` against real Credential Manager and CI-rendered snapshots); owner demo; owner replies "approved".

**Owner request during Phase 3 — Channel Trending (2026-11-08):** Outliers, Replicate / "milky" videos and New Ideas. Owner decisions: **own channels only** for outliers (YouTube data policy, ADR-0015), **variations of own winners** with an originality guard (similarity ≤ 0.70 + owner value-add; near copies refused), **plan + screens now**. Done: US-4.6, ADR-0025, FRONTEND_SPECIFICATION §32 (test plan moved to §33), A08 variation mode, API endpoints, schema (`video_ideas.source` + REPLICATE, `based_on_youtube_video_id`, `variation_kind`, `similarity_to_source`), roadmap (Phase 7 variation mode, Phase 13 outliers), compliance line; **Page 32 Channel Trending** (Channels group) with three keyboard-accessible tabs on sample data and the replicate dialog (the guard refuses "Updated version" in the sample). Tests: Vitest 23, Playwright 128 route×state cases + axe for page 32. Also fixed: the menu highlighted "Channel Manager" on every /channels/… page (links now match exactly).

**Demo script (owner, Windows):** `git -C "D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app" pull` → `tubeforge.ps1 setup` (creates the master key; asks your e-mail, name and a password) → `tubeforge.ps1 start` → sign in → Settings › Two-factor sign-in › scan the QR with a phone authenticator, enter the code, save the recovery codes → press Emergency Stop (red banner on every page; open a second tab to see it appear there too) → clear it (asks your password and code) → Audit & Security Center › Verify chain → Channels › Channel Trending: switch tabs, press Replicate this, try "Updated version" (refused as too similar) and "New angle" (created).

### Phase 4 — Channel onboarding, OAuth & quota ledger · report 2026-11-09 · branch `claude/vigilant-tesla-lkhgme` · merged to `main` (PR #8) by the owner 2026-11-09 ("merged, go ahead with phase 5") · manual real-OAuth test still open

**Plan (from IMPLEMENTATION_ROADMAP Phase 4), in four steps:**
- **P4-A YouTube core** ✅ — `youtube/errors.py` (classification §7), `youtube/quota.py` (buckets, PT day + PKT reset time, reservations under an advisory lock, ledger, research share, forecast), migration 0004 seeding `quota_config` with the costs verified 2026-11-08, `youtube/client.py` `SafeYouTubeClient` preflight I-1…I-12 (I-4 refuses non-test uploads until Phase 9; I-12 refuses auto-publish until Phase 14) and an httpx REST client (ADR-0026). ORM models for the Phase 4 tables. 5-second private test clip (`youtube/assets/test_clip.mp4`, own artwork). `tzdata` added so time zones work on Windows.
- **P4-B OAuth** ✅ — OAuth client registration (secret encrypted), PKCE loopback flow (`/oauth/callback` on 127.0.0.1:8765), identity confirmation via `channels.list mine=true`, token refresh → NEEDS_REAUTH, revoke + 7-day data deletion, token-health job with Testing-mode 7-day warnings. Mocked Google in tests (a fake that verifies PKCE). Added `GET /channels/{id}/oauth/identity` so the owner sees the signed-in channel before confirming; `tubeforge.notifications.notify_owners` (dedup window) shared by preflight and OAuth.
- **P4-C Channels & test upload** ✅ — Channels API (CRUD, start-onboarding/pause/resume/disconnect/reconnect, publishing rules, private-only/mode with step-up), 10 onboarding steps, resumable private test upload job (8 MiB chunks, persisted offset, resume, idempotent) with a fault-injection test, retention jobs (cache purge, deletion tasks, 30-day re-auth check), minimal notifications + bell count. Built: `channel_lifecycle.py` (allowed moves + workflow_transitions), `youtube/uploads.py` (resumable engine, encrypted session URI, offset committed after each chunk), `youtube/retention.py`, `/uploads`, `/quota`, `/notifications`; the upload job is created in the same DB transaction as the upload record (`queue.defer_in_transaction`). Duplicate guard via the uploads playlist after an expired session is deferred to Phase 10 (a test upload fails instead).
- **P4-D Web, site & docs** ✅ — Channel Manager + Onboarding pages on the real API, bell, `site/privacy.html` + `site/terms.html` (DP-5), owner guide for the Google Cloud project (no billing), OAuth Desktop client and test channel, e2e + CI, phase report. Then the one **manual** real OAuth + private upload on the owner PC.

**Decisions so far:** ADR-0026 (httpx instead of the Google client libraries). Fix: the schema generator now keeps commas inside quoted defaults together (`min_audit_scores`).

**Phase 4 report (TESTING_AND_QA §7)**

1. **Modules implemented**
   - `youtube/errors.py`: sorts Google errors into classes (§7).
   - `youtube/quota.py`: buckets, the PT quota day with the reset time also shown in PKT, reservations under an advisory lock, a ledger row for every call, the research share, and a 7-day forecast.
   - `youtube/client.py`: **SafeYouTubeClient** runs preflight checks I-1…I-12 before every upload, and its httpx client only talks to allowed hosts (ADR-0026).
   - `youtube/oauth.py`: PKCE loopback sign-in, encrypted tokens, identity confirmation, refresh, NEEDS_REAUTH handling, the token health job, and disconnect with revoke.
   - `youtube/uploads.py`: resumable upload engine and the private test upload.
   - `youtube/retention.py`: DP-2/3/4 retention rules.
   - `channel_lifecycle.py`: channel state machine and onboarding steps.
   - `notifications.py`: shared helper for in-app notifications.
   - `queue.defer_in_transaction`: creates a queue job in the same transaction as the database row.
   - Worker jobs: `yt.upload`, plus 5 scheduled maintenance jobs.
   - Web, now on the real API: Channel Manager, Channel Onboarding (10 steps with official help links, OAuth client form, privacy link, Connect with Google, identity confirmation, live test-upload progress), Notification Center, the bell, the channel switcher, the quota meter, and banners. The top-bar channel is shared by all channel pages.
   - The app has its own favicon.
   - `site/privacy.html` and `site/terms.html` meet the DP-5 checklist, published by the `pages` workflow.
2. **Files created/modified:**
   - Backend: `apps/api/tubeforge/{youtube/*, channel_lifecycle.py, notifications.py, api/v1/{oauth,channels,uploads,notifications}.py, queue/__init__.py, db/models}` and migration `0004_seed_quota_config`.
   - Workers: `workers/tubeforge_workers/{tasks,maintenance}.py`.
   - Web: `apps/web/src/{pages/channels/*, pages/NotificationsPage.tsx, lib/channel.tsx, lib/useBackend.ts, components/{TopBar,Banners,Navigation}.tsx, mocks/testApi.ts, i18n/en.json}`, e2e (`global-setup.ts` seeding, `helpers.ts`, `routes.spec.ts`, `stateful.spec.ts`).
   - Site and CI: `site/*`, `.github/workflows/pages.yml`.
   - Docs: ADR-0026, `docs/OWNER_GUIDE_YOUTUBE_CONNECTION.md`, YOUTUBE_API_INTEGRATION, OAUTH_SECURITY, BACKEND_SPECIFICATION, WORKFLOW_STATE_MACHINE, DEPLOYMENT_GUIDE, CLAUDE.md.
   - Generator: `tools/gen_schema_sql.py` (quote-aware split).
3. **Database changes:** migration 0004 seeds `quota_config` with Google's limits and costs, verified 2026-11-08. The ORM now has models for the 17 Phase 4 tables (DDL from Phase 3). There were no schema-document changes.
4. **APIs implemented:** 30 new routes.
   - OAuth (7): clients ×3, start, incremental, identity, confirm-identity, plus health and the public `/oauth/callback` page.
   - Channels (13): CRUD, 5 commands, mode, private-only, publishing rules ×2, accept-auto-rules, onboarding ×2, test-upload, delete-api-data.
   - Uploads ×2, `/quota`, and notifications ×4.
5. **Agents created:** none (Phase 5).
6. **Tests executed (Linux, this session):**
   - **Python: 177 passed** (+55 contract subtests). New tests:
     - each check I-1…I-12 on its own;
     - 20 workers racing for the last quota units (exactly the remaining 5 win);
     - 13 OAuth tests against a fake Google that checks PKCE, including single-use state, expired state, a forged verifier, an un-ticked permission box, and incremental consent;
     - 14 channel and upload tests, including fault injection (connection reset mid-chunk, a 503, a worker crash and resume: every byte sent once, one upload session), refusals, guards, retention and the bell;
     - DP-5 site content.
   - The contract test found two real bugs, both fixed: a NUL byte in a log filter caused a 500, and on an unconnected channel the test upload stopped before its safety checks ran, so no refusal was recorded.
   - **Web unit: 29 passed.**
   - **Playwright, local run against the real API:**
     - **204 passed** on desktop and mobile: 32 routes × 4 states, axe light and dark, mobile, shell.
     - **5/5 stateful**, including the new channel-setup flow (Google's page intercepted) and the bell.
     - 8 visual snapshots differ as expected and are re-rendered by CI.
7. **Free-tier services used:**
   - YouTube Data API v3 (free quota), Google OAuth, GitHub Pages and GitHub Actions (free for public repositories).
   - New dependencies: `httpx` (BSD-3-Clause, now used at runtime) and `tzdata` (Apache-2.0). Without `tzdata`, Windows has no time zones, so this also fixes a latent Phase 3 bug.
   - **This phase introduces no paid dependency: ✔**
8. **Resource consumption:** same processes. Uploads run on the light worker's `youtube` queue, one per channel at a time, in 8 MiB chunks, so memory stays flat.
9. **Known limitations:**
   - Only **private test uploads** pass the checks. Non-test uploads are refused at I-4 until the auditors exist (Phase 9), and auto-publish is refused at I-12 until Phase 14.
   - If an upload session expires (about a week), the test upload fails and the owner presses the button again. The duplicate guard through the uploads playlist arrives with real uploads (Phase 10).
   - The 30-day re-authorisation check covers stored video IDs. Analytics data arrives in Phase 13.
   - Notifications are in-app only. Telegram and e-mail delivery arrive in Phase 12.
   - Help links: 8 of the 14 checked load and are on topic. The consent-screen page was replaced by Google's "Manage App Audience" page, which is linked from the old one. The console, `policies.google.com`, `myaccount`/`security.google.com`, `youtube.com/t/terms` and `studio.youtube.com` could not be reached from the build machine. Those are the addresses Google's own documentation cites.
   - Visual snapshot baselines changed: the top bar now shows the real channel. CI re-renders them.
10. **Remaining tasks for Phase 4 acceptance:**
   - CI green, including refreshed snapshots.
   - **The owner's one manual test** on the PC: real OAuth with the test channel and one private upload. The steps are in `docs/OWNER_GUIDE_YOUTUBE_CONNECTION.md`. The result gets recorded here.
   - The owner fills in name, e-mail and date in `site/privacy.html` and `site/terms.html`, then turns on GitHub Pages.
   - The owner replies "approved".

**Demo script (owner, Windows):**
1. `git -C "D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app" pull`, then `tubeforge.ps1 setup` and `tubeforge.ps1 start`.
2. Sign in, then go to **Channels › Add channel** ("My Test Channel", tick "This is my test channel").
3. Follow the 10 steps (the guide has the clicks), then **Connect with Google**, then confirm your channel.
4. **Run test private upload**. The progress bar fills; then **Open in YouTube Studio** shows a private 5-second video.
5. The bell shows "Private test upload done", and the top bar's quota meter moves.
6. Optional: Channels › Pause and Resume.

**Manual real-OAuth test (owner PC):** *not yet run — to be recorded here.*

### Phase 5 — Orchestrator & agent infrastructure · report 2026-11-10 · branch `claude/vigilant-tesla-lkhgme` · merged to `main` (PR #9) · ✅ approved by the owner 2026-11-10 (demo run on the owner PC, steps 1–5)

**Plan (from IMPLEMENTATION_ROADMAP Phase 5), in four steps:**
- **P5-A Orchestrator** ✅ — built: `orchestrator/{machines,guards,engine,approvals,reconciler,controls}.py`; channel helpers, OAuth, retention and the upload runner now change states only through the engine; jobs `orch.reconcile` (2 min) and `orch.approvals_expire` (hourly). Tests: 191 table-driven edge/guard cases, every unlisted (state, event) pair, Emergency Stop per edge, idempotency, actor rules, mode gates, universal states, approval hash invalidation, reconciler lost/stalled/ES, property tests, upload stopped by Emergency Stop at a chunk boundary and resumed. Implementation notes in WORKFLOW_STATE_MACHINE §9a.
  - The 10 state machines of WORKFLOW_STATE_MACHINE as code tables: Channel, Idea, Video Project (with external editing), Render, Upload, Notification delivery, Approval, Voice Profile, Stock Purchase.
  - One transition engine: row lock, Emergency Stop rule, actor rules, mode gates [S]/[F], guard registry, `workflow_transitions` + audit in the same transaction, idempotent replay.
  - Approval requests bound to a subject hash: decide, invalidate, expire.
  - Reconciler: every 2 minutes, re-enqueue lost jobs exactly once.
  - Emergency Stop and kill switches also checked inside running jobs (the upload stops at a chunk boundary).
  - Table-driven tests: every allowed transition, each guard violated on its own, every illegal pair, Emergency Stop, idempotency. Property tests. A reconciler crash test.
- **P5-B AI Provider Gateway** ✅ — built:
  - `gateway/{core,registry,limits,cache}.py` and adapters for Gemini, Groq and Ollama.
  - Migrations: 0006 repairs two tables the generator had cut short; 0007 seeds the registry and placeholder limits.
  - ADR-0027: local model Qwen2.5-1.5B, Apache-2.0.
  - New dependency `jsonschema-rs` (MIT).
  - Tests: 12 adapter tests and 15 pipeline tests, plus a check that every table in a real database matches the generated schema.
  - Registry seeded from FREE_TIER_PROVIDER_MATRIX; encrypted credentials.
  - Atomic usage reservation and settlement against limits.
  - Cache; JSON-schema validation with one repair attempt; fallback chains; local-only, data-use and licence rules.
  - Adapters for Gemini (free tier), Groq (free plan) and Ollama (local), all over httpx and tested against fakes.
- **P5-C Agent framework and cost safety** ✅ — built:
  - `workers/tubeforge_agents/{catalogue,prompting,base,hello}.py`, with prompts in `prompts/T00_HELLO/`.
  - `workers/tubeforge_auditors/a32_cost.py`.
  - `gateway/{paid,indicators}.py`.
  - Migration 0008 seeds the 33 agent configurations.
  - Jobs `agent.run` and `a32.usage_scan`.
  - New dependency `jinja2` (BSD-3).
  - Tests: 10 unit and 10 integration. They include the roadmap demo: a limit of 2 a day, the third run waits and you are notified, then a switch to the local model, then Emergency Stop. They also cover the two-step paid activation (too soon, wrong phrase, no cap, expired step 1), paid calls capped and paused at the cap, paid-tier signs in responses, and A32 thresholds and reminders.
  - Fixes: A32 alerts were not de-duplicated. A NUL byte in the login e-mail caused a 500; it now gets a 400, and any NUL that still reaches PostgreSQL gets a 400 everywhere. Found by the contract test.
  - AgentTask base, schemas, versioned prompt files, `agent_runs` with redacted input and output, metrics, and a "hello" test agent.
  - Paid (Tier P) two-step activation with a 60-second gap, budgets, and the A32 paid-indicator detector.
- **P5-D Web and report** ✅ — built:
  - APIs: `api/v1/agents.py` (7 routes) and `api/v1/providers.py` (12 routes).
  - **Agent Control Center** on the real API:
    - every agent with its kind, state and 24-hour stats;
    - Pause/Resume through the same AGENT kill switch the workers obey;
    - a config dialog: provider chain (reorder, add, remove), runs and tokens per day; saved with If-Match;
    - a test run for the hello agent;
    - recent runs with redacted input and output.
  - **Cost & Usage Manager** on the real API:
    - a spend banner;
    - one write-only key per provider family;
    - a row per model with on/off, usage meters, daily limits, the "placeholder" note and "I checked it today";
    - the two-step paid activation (acknowledge, then the typed phrase, a cap and a 60-second countdown) and "Switch off now";
    - YouTube quota meters and monthly budgets.
  - Fix found by the contract test: provider codes contain `/`, so `PATCH /providers/x/verify` was read as provider `x/verify` and got 403 instead of 405. A path converter now never treats `verify`, `credentials` or `paid-activation` as part of a code.

**Fixes found while building:**
- **Truncated tables.** The schema generator ended a table at `);` inside a comment and mis-split column lists. `provider_credentials` had **no columns** in every database since Phase 3, and `seo_packages` lost 13 columns in Phase 4. The generator now reads table bodies properly. Migration 0006 rebuilds both tables (no data existed). A new test compares every table's real columns with the generated schema.
- **Enum check on the wrong column.** the schema generator put an enum check on the first text column of a line that declares two. `voice_profiles.label` and `notification_deliveries.channel` got the state checks. The generator is fixed, and migration 0005 repairs existing databases.

**Phase 5 report (TESTING_AND_QA §7)**

1. **Modules implemented**
   - **Orchestrator** (`orchestrator/`): 10 state machines as code tables, one transition engine (row lock, Emergency Stop, actor rules, [S]/[F] mode gates, 51 guards, transitions + audit in one transaction, idempotent replay), hash-bound approvals, and a reconciler for lost and stalled jobs. Channel, OAuth, retention and upload code now move states only through the engine.
   - **AI Provider Gateway** (`gateway/`):
     - one pipeline for every AI call: stop checks → policy → key → cache → usage reservation → adapter → schema validation with one repair → settle;
     - adapters for Gemini, Groq and Ollama;
     - two-step paid activation, budgets, and paid-tier detection.
   - **Agents** (`workers/tubeforge_agents`): catalogue of 32 agents plus the hello test agent, versioned prompts with untrusted-input fencing, `run_agent()` (refusal, redaction, waiting for quota, Emergency Stop).
   - **A32 cost monitor** (`workers/tubeforge_auditors/a32_cost.py`): alerts at 70 / 90 / 100 %, re-verify reminders, a day-1 check of the bank statement.
   - **Web:** Agent Control Center and Cost & Usage Manager now run on the real API. New `Meter` component.
2. **Files created/modified:**
   - Backend: `apps/api/tubeforge/{orchestrator/*, gateway/*, api/v1/{agents,providers}.py, main.py, channel_lifecycle.py, youtube/{oauth,uploads,retention}.py, db/models}` and migrations 0005–0008.
   - Workers: `workers/tubeforge_agents/*` (with `prompts/T00_HELLO/`), `workers/tubeforge_auditors/a32_cost.py`, `workers/tubeforge_workers/{tasks,maintenance}.py`.
   - Web: `apps/web/src/{pages/agents/*, pages/usage/*, components/Meter.tsx, lib/api/client.ts, pages/registry.ts, app/routes.tsx, mocks/testApi.ts, i18n/en.json}`, e2e (`helpers.ts`, `stateful.spec.ts`).
   - Contract: `packages/shared/openapi.json`, `openapi.stub.json`.
   - Generator: `tools/gen_schema_sql.py`.
   - Docs: ADR-0027, WORKFLOW_STATE_MACHINE §9a, BACKEND_SPECIFICATION §4.16–4.17, AI provider and cost specs, CLAUDE.md.
3. **Database changes:**
   - 0005 moves two enum checks to the right columns.
   - 0006 rebuilds `provider_credentials` and `seo_packages`, which the generator had cut short (no data existed).
   - 0007 seeds the provider registry and placeholder limits.
   - 0008 seeds the 33 agent configurations.
   - A new test compares every real table with the generated schema.
4. **APIs implemented:** 19 new routes.
   - Agents (7): list, get, edit (If-Match), prompts, test run, runs list, run detail.
   - Providers (12): list, edit, key save/remove, verify, paid step 1/step 2/switch-off, usage, cost summary, budgets get/set.
5. **Agents created:**
   - `T00_HELLO`, a test agent that runs end to end through the gateway.
   - A32, the cost and usage monitor, runs every 15 minutes.
   - The other 31 agents are configured (chain, limits) but have no handler until their phases. Test runs answer `NO_HANDLER`.
6. **Tests executed (Linux, this session):**
   - **Python: 283 passed** (+265 contract subtests). New tests:
     - 191 table-driven state-machine cases;
     - gateway pipeline and adapter tests;
     - agent framework tests;
     - paid activation tests (too soon, wrong phrase, no cap, expired step 1, capped and paused at the cap);
     - A32 thresholds and reminders;
     - 6 API tests for agents and providers;
     - the roadmap demo (a limit of 2 a day, the third run waits, switch to the local model, then Emergency Stop).
   - The contract test found 2 real bugs, both fixed: a NUL byte in the login e-mail caused a 500, and the provider-route clash described above.
   - **Web unit: 32 passed.**
   - **Playwright, local run against the real API:**
     - **204 passed** on desktop and mobile: routes × states, axe light and dark, mobile.
     - **6/6 stateful**, including the new "Agent Control Center and Cost & Usage on the real backend" test: set an agent's daily runs, queue a hello test run, save a key, and paid step 1 (with re-auth) → step 2 locked by the countdown.
     - 8 visual snapshots differ only by local fonts; CI renders the baselines.
   - **Checks:** ruff, mypy --strict, eslint, tsc, `api:check`, traceability, pre-commit (gitleaks), pip-audit, pnpm audit and the licence check are all green.
7. **Free-tier services used:**
   - Gemini API free tier and Groq free plan, both off until the owner saves a key, and both capped by the owner's daily limits. Ollama runs locally for free.
   - New dependencies: `jsonschema-rs` (MIT) and `jinja2` (BSD-3). The local model Qwen2.5-1.5B is Apache-2.0 (ADR-0027).
   - Paid (Tier P) providers stay off. They switch on only through the two-step activation with a monthly cap.
   - **This phase introduces no paid dependency: ✔**
8. **Resource consumption:**
   - Same processes as before.
   - New scheduled jobs are light: the reconciler every 2 minutes, A32 every 15 minutes, approvals expiry hourly.
   - Ollama (optional) needs about 1.5 GB of RAM while a model is loaded.
   - No AI provider was called for real in this session. Tests use fakes.
9. **Known limitations:**
   - The provider limits in the database are **placeholders** until the owner enters the real numbers from the Gemini and Groq pages. The page marks them.
   - Only the hello agent can run. Real agents arrive with their phases (Phase 6 onwards).
   - Paid costs are estimated from per-token prices in the registry. The owner checks the bank statement on day 1 (A32 reminds).
   - Visual snapshot baselines changed for the two new pages. CI re-renders them.
10. **Remaining tasks for Phase 5 acceptance:**
   - CI green, including refreshed snapshots.
   - The owner runs the demo below and replies "approved".
   - Still open from Phase 4: the manual real-OAuth + private upload test.

**Demo script (owner, Windows):**
1. `git -C "D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app" pull`, then `tubeforge.ps1 setup` (runs the new database upgrades) and `tubeforge.ps1 start`.
2. Sign in, then open **Cost & Usage**. Every row shows "placeholder" and all paid providers are off.
3. Optional, free: get a Gemini key from Google AI Studio (in a Google Cloud project with **no** billing) and paste it into the Gemini **API key** box, then **Save key**. Then open the Gemini rate-limit page, type today's real requests and tokens per day into one model row, and press **I checked it today**.
4. Open **Agents**. Find **T00_HELLO** and press **Test run**, type a name and press **Run**. It appears in **Recent runs** within a few seconds. With a key (or Ollama) it shows **Done** and a greeting. Without either it shows **Failed** with "no provider available", which is the safe outcome.
5. Press **Pause** on T00_HELLO, then **Resume**. This uses the same switch the workers obey.
6. Press **Emergency Stop** in the top bar, then start another test run: it shows **Stopped**. Clear Emergency Stop.
7. Paid safety, look only: on a paid row, tick the box and press **Step 1: confirm**. Step 2 counts down 60 seconds and asks for the typed phrase and a cap. **Do not finish it.** Press **Switch off now**.

**After the merge (owner PC, 2026-11-10):** the first `setup` stopped at `uv sync` because TubeForge was still running and Windows locks `tubeforge-api.exe` (os error 32). Fix: `setup` now stops TubeForge first and starts it again at the end. Workaround on the old copy: `stop`, then `setup`.

### Phase 6 — Niche discovery & trends · in progress · branch `claude/vigilant-tesla-lkhgme`

**Owner direction (2026-11-10):** the owner will create a **new YouTube channel from scratch through TubeForge**. Discovery picks the niche with evidence, the owner approves a blueprint, and TubeForge creates the channel record. The owner then creates the YouTube channel and connects it as the **test channel** (Phase 4 onboarding). Private test uploads go only there. Later phases can upgrade it to a real, public channel, but only through the normal gates (auditors from Phase 9, publishing from Phase 12) and the owner's explicit choice. First discovery: the owner chose "let TubeForge suggest" (2026-11-10); the roadmap demo still uses "English, personal finance for students" as a test case.

**Plan (from IMPLEMENTATION_ROADMAP Phase 6), in four steps:**
- **P6-A Research fetcher and sources** ✅ — built (2026-11-10):
  - `research/{net,fetcher,sanitize,sources,wikipedia,rss,trends}.py`, `api/v1/research.py` (4 routes), migration 0009 (registry seed), job `mnt.retention.purge_research_docs`;
  - tests: 61 unit (address rules, IP forms, redirects re-checked, size/time/type caps, peer re-check, sanitiser, safe feed parsing) and 7 integration (seed, pageviews stored as evidence, Emergency Stop and switched-off sources fetch nothing, RSS items, 90-day purge, API with re-auth approval, anti-scraping, roles);
  - the owner chose **"let TubeForge suggest"** for the first discovery (no fixed language or audience);
  - open: Wikimedia's terms and User-Agent policy pages could not be opened from the build machine, so the owner confirms them on the Sources page (step D), and may add a contact to the User-Agent (`research_contact`).
- **Plan for P6-A:**
  - one fetcher behind the allowlist, with an SSRF guard, sanitiser and untrusted-text wrapper;
  - a source registry and its API;
  - adapters for Wikipedia pageviews and RSS;
  - a Trends adapter that stays off unless the owner approves it.
- **P6-B Discovery agents and scoring:**
  - agents A02, A03, A05, A06 and A07 on the Gateway;
  - deterministic scoring and rescore, with weight profiles;
  - evidence on every candidate;
  - a forbidden-phrase scan.
- **P6-C Competitor lookup (A04):**
  - one public item per lookup, kept for 30 days;
  - a policy banner;
  - no aggregation and nothing fed into scores (ADR-0015), enforced by a static check and a test.
- **P6-D Web and report:**
  - Discovery, Research, Trends, Strategies and Branding Studio (blueprint editor) on the real API;
  - approving a blueprint creates the channel;
  - e2e tests, docs, phase report.

## Resource consumption

| Resource | Used |
|---|---|
| Paid services | None |
| Free-tier APIs | None called yet (research used public web pages only) |
| Idle RAM (Phase 1, Linux) | ≈ 550 MB total (API + 2 workers + PostgreSQL) |
| YouTube API quota | 0 units |
