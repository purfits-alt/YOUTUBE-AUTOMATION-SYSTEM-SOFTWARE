# TubeForge — Project Progress

> Living document. Updated at every checkpoint and at the end of every phase.

**Current phase:** Phase 2 — Frontend shell
**Current step:** Phase 2 built (incl. owner's premium design + Lottie request). Waiting for CI and owner approval ("approved").
**Last updated:** 2026-11-08

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


### Phase 2 — Frontend shell · report 2026-11-08 · branch `claude/vigilant-tesla-lkhgme` · ⏳ awaiting owner approval

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
   - Visual snapshots are Linux-rendered (CI is Linux). If CI's Chromium renders differently, refresh them with `--update-snapshots`.
10. **Remaining tasks for Phase 2 acceptance:** CI green on the PR; owner demo below; owner replies "approved".

**Demo script (owner):** `git pull` in `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app` → install Node.js 22 LTS from nodejs.org and then `npm install -g pnpm@10.28.0` (one time, free) → `tubeforge.ps1 setup` (now builds the dashboard) → `tubeforge.ps1 start` → open http://127.0.0.1:8765 → click through every sidebar item → use "Scenario (dev)" bottom-right to show empty / loading / error → press Emergency Stop (add a reason) → clear it (any password) → `Ctrl+K` and search "thumb" → switch Theme to Dark → make the window phone-sized.

## Resource consumption

| Resource | Used |
|---|---|
| Paid services | None |
| Free-tier APIs | None called yet (research used public web pages only) |
| Idle RAM (Phase 1, Linux) | ≈ 550 MB total (API + 2 workers + PostgreSQL) |
| YouTube API quota | 0 units |
