# CLAUDE.md — TubeForge (YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE)

## What this is
TubeForge is a **local-first, free-to-run, AI-assisted YouTube production and channel-management platform** for one owner, running natively on Windows. The owner directs and approves the work. It is a **standalone project**: never use, import, copy or connect to SEMRS OS or any other product's code, database, auth, APIs, agents, notifications, infrastructure or deployment.

Planning docs live in `docs/` (start with `docs/PROJECT_PROGRESS.md`, then `docs/IMPLEMENTATION_ROADMAP.md`). Accepted decisions are in `docs/adr/`.

## Repo layout (created in Phase 1)
```
apps/api/        FastAPI backend (tubeforge package): api/v1, orchestrator, gateway, youtube, auth, secrets, audit
apps/web/        Vite + React + TypeScript SPA (served by the API in production)
workers/         tubeforge_agents (A02–A28 handlers), tubeforge_auditors (A21–A23, A30–A32), tubeforge_media (render, tts, voice, captions, thumbnails), tubeforge_notify
packages/shared/ enums.json, JSON Schemas (timeline, blueprint, agent I/O), generated TS client
infra/           windows/tubeforge.ps1 (setup|start|stop|status|doctor|backup|restore|update), compose/ (Linux dev/CI)
site/            privacy.html, terms.html (GitHub Pages)
docs/            specs, ADRs, progress
```
Owner install root: `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE` (the path has spaces: always quote paths, and use argv lists for subprocesses).

## Commands (verified in Phase 1 — keep this section current)
| Task | Command |
|---|---|
| Install deps | `uv sync` · `pnpm -C apps/web install` |
| Database migrations | `uv run tubeforge-db upgrade` · `uv run tubeforge-db downgrade -1` · `uv run tubeforge-db current` |
| Run API (dev) | `uv run tubeforge-api --reload` → http://127.0.0.1:8765 (`/healthz`, `/readyz`, `/api/docs`) |
| Run workers (dev) | `uv run tubeforge-worker --queues light` · `uv run tubeforge-worker --queues heavy` (`--once` = drain and exit) |
| Run web (dev) | `pnpm -C apps/web dev` → http://127.0.0.1:5173 (proxies the API) |
| Build web | `pnpm -C apps/web build` (the API serves `apps/web/dist`) |
| Lint & types | `uv run ruff check . && uv run ruff format --check . && uv run mypy` · `pnpm -C apps/web lint && pnpm -C apps/web typecheck` |
| Python tests | `TUBEFORGE_TEST_DATABASE_URL=postgresql+psycopg://…/tubeforge_test uv run pytest` (integration tests wipe that DB) · unit only: `uv run pytest -m "not integration"` |
| Web tests | `pnpm -C apps/web test` · e2e (API running with built web): `pnpm -C apps/web e2e` (routes×states, axe, mobile, visual) · new snapshots: `pnpm -C apps/web e2e --update-snapshots` |
| API client (stub until Phase 3) | `pnpm -C apps/web api:gen` (from `packages/shared/openapi.stub.json`) · CI: `pnpm -C apps/web api:check` |
| Lottie animations | `uv run python tools/gen_lottie.py` (own artwork → `apps/web/src/assets/lottie/`) |
| Mock data / states | Phase 2 data comes from MSW (`apps/web/src/mocks`); `?scenario=empty\|loading\|error\|success` or the dev switcher |
| Docs checks | `uv run python tools/check_traceability.py` |
| Security | `uv run pre-commit run --all-files` (gitleaks, ruff, traceability) · `uv run pip-audit --skip-editable` · `pnpm -C apps/web audit --audit-level high` · licences: `tools/check_licenses.py` |
| Local Postgres for dev (Linux) | `docker compose -f infra/compose/docker-compose.dev.yml up -d` |
| Windows (owner PC) | `tubeforge.ps1 doctor` · `setup` · `start` · `stop` · `status` (in `infra/windows/`) |

## Coding standards
- **Python 3.12:** ruff (lint + format), mypy `--strict`, pytest (+ hypothesis). Pydantic v2 for all I/O. SQLAlchemy 2.0 typed ORM. Alembic migrations with downgrades. Async for I/O; heavy work only in workers.
- **TypeScript:** strict, eslint + prettier, `tsc --noEmit`. Use only the generated API client. Forms use react-hook-form + zod.
- Small, focused commits. Each one passes lint, types and tests.

## NEVER
- Never add a **paid** dependency, service or API by default, enable billing, or auto-upgrade a plan. Tier P providers stay disabled (two-step owner activation only).
- Never hard-code or commit secrets (tokens, keys, passwords, `.env`). The repo is **public**.
- Never call AI providers outside the **AI Provider Gateway**, or YouTube outside **SafeYouTubeClient**, or the internet outside the registered adapters and allowlist.
- Never set YouTube privacy implicitly. `privacyStatus`, `selfDeclaredMadeForKids` and `containsSyntheticMedia` are always explicit. `publishAt` is only private and ≥ now + 15 min.
- Never bypass, disable or weaken auditors, approvals, Emergency Stop or kill switches.
- Never scrape YouTube or Google, never download or store YouTube videos, never aggregate other channels' API data (ADR-0015).
- Never clone any voice except the owner's own, via live-recorded consent (ADR-0019).
- Never let an agent publish, buy, delete YouTube content, change privacy, or change permissions.
- Never let an asset without a rights record into a render.
- Never skip or silently `xfail` a failing test.
- Never upload for real except to the **test channel**, and only when a phase demo requires it.

## Definition of Done (every task)
Code + tests (new and existing passing) + docs updated (relevant spec + `PROJECT_PROGRESS.md`) + ADR if a decision was made + **free-tier check** ("introduces no paid dependency ✔") + lint, types and security checks green.

## How to work
1. Read the phase in `docs/IMPLEMENTATION_ROADMAP.md` and the referenced spec sections.
2. Write a short plan in `PROJECT_PROGRESS.md`.
3. Implement in small commits on a phase branch. Run tests as you go.
4. Run the full phase test suite. Write the phase report (10 items, TESTING_AND_QA §7).
5. Show the owner the results and the demo script, then **stop** until the owner replies "approved".

Precedence when documents disagree: owner's latest instruction > checkpoint decisions/ADRs > specs > master prompt. Fix the lower document in the same change. Unknown requirement → ask the owner and record it as an open question. Don't guess.
