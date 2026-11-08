# Testing & QA Strategy

**Version:** 1.0 (approved at C6, 2026-11-08) · **Date:** 2026-11-08 · **ADR:** 0017

## 1. Test pyramid & tools
| Level | Tools | Runs where | Target |
|---|---|---|---|
| Unit (Python) | pytest, hypothesis (property tests) | CI (Linux + Windows subset), local | ≥ 85 % line coverage on `orchestrator`, `gateway`, `youtube`, `auditors`, `secrets`, `auth` (overall ≥ 75 %) |
| Unit (Web) | Vitest + Testing Library | CI | Key components and hooks |
| Integration (API + DB + queue) | pytest + httpx + real PostgreSQL 16 (CI service container / local install) + Procrastinate in-process worker | CI Linux; queue smoke on Windows | All endpoints happy path + guards |
| Contract | schemathesis-style tests against committed `openapi.json`; generated TS client compiled with `tsc --strict` | CI | 0 undocumented responses |
| Agent golden tests | Mocked Gateway with recorded fixtures, fixed seeds, schema validation | CI | All 17 prompted agents (AGENT_PROMPTS test table) |
| Adversarial | Prompt-injection pages, forbidden phrases, disclosure cases, policy F3 cases, script craft cases | CI | 100 % pass |
| Media | ffmpeg/ffprobe on fixture media (short clips) | CI Linux (ffmpeg installed) + Windows smoke | Durations, streams, loudness ±1 LU, defect detection |
| E2E (UI) | Playwright (Chromium) + MSW (Phase 2) / real API (Phase 3+) | CI | 31 routes × 4 states; critical journeys |
| Accessibility | axe-core in Playwright | CI | 0 serious/critical |
| Security | authz matrix, CSRF/Host, lockout, encryption tamper, redaction, outbound allowlist, anti-scrape, gitleaks, pip-audit, pnpm audit, licence scan | CI | 0 HIGH/CRITICAL |
| Migrations | Alembic upgrade head → downgrade base → upgrade head; schema snapshot diff | CI | Pass |
| Backup/restore | Scripted dump → restore on empty DB + key file → tokens decrypt | CI (Linux) + Phase 15 manual on Windows | Pass |
| Manual (real services) | Real OAuth + private upload to **test channel**; scheduled upload; Telegram message | Owner PC, at Phases 4, 12, 14, 15 | Recorded in PROJECT_PROGRESS |
| GPU/model-heavy | TTS, voice clone, Whisper, local LLM | **Local only** (not in CI) | Smoke + benchmark |

## 2. Mandatory "proof" tests (from the brief & PRD)
| ID | Proves | Phase |
|---|---|---|
| T-BLOCK | A video that fails a blocking audit cannot be uploaded through any API path | 11 |
| T-LIMIT | A provider pauses at its free limit and the owner is notified; fallback used | 5 |
| T-PRIV | No `videos.insert` can be sent without explicit `privacyStatus`, `selfDeclaredMadeForKids`, `containsSyntheticMedia` | 4/12 |
| T-DUP | No duplicate upload (DB unique + idempotency + duplicate guard after expired session) | 4/12 |
| T-STOP | Emergency Stop halts all jobs within 30 s and blocks every external mutation | 5 |
| T-PAID | Tier P providers impossible without 2-step activation; stock purchase impossible at budget 0 | 5/8 |
| T-AGG | YouTube lookup data never enters scores or cross-channel aggregates | 6 |
| T-RET | Non-authorized API data purged ≤ 30 days; disconnect deletes within 7 days | 4 |
| T-CONSENT | Voice clone impossible without live-recorded consent with matching code and speaker | 8 |
| T-RIGHTS | Asset without rights cannot enter a timeline/render | 8/9 |
| T-PROMISE | Script validators: hook 10–15 s, promise ≤ 15 s (Shorts 3 s), re-hooks bands, all loops closed | 7 |
| T-APPROVAL | Any change after approval invalidates it (hash mismatch) | 5/12 |

## 3. CI pipeline (GitHub Actions, free for public repo)
```
on: [push, pull_request]
jobs:
  lint:        ruff, mypy --strict, eslint, prettier --check, tsc --noEmit
  unit:        pytest -m "not integration and not media" ; vitest
  integration: services: postgres:16 ; pytest -m integration ; contract tests
  media:       apt ffmpeg ; pytest -m media
  e2e:         build web ; start api (test mode, mocked providers) ; playwright test --trace off
  security:    gitleaks ; pip-audit ; pnpm audit --audit-level high ; licence scan
  windows:     runs-on windows-latest ; install to "C:\Tube Forge Test\" (path with spaces) ;
               postgres (choco/zip) ; queue smoke ; ffmpeg smoke ; healthz
```
Branch protection on `main`: all jobs green + 1 review (owner) for merges. Mocked providers only. No real API keys in CI (secrets scanning would block them anyway).

## 4. Test data & fixtures
- `tests/fixtures/sources/` sanitised HTML/RSS samples, including injection pages.
- `tests/fixtures/media/` tiny clips (2–5 s) with known defects: black, freeze, silence, wrong aspect, loud/quiet.
- `tests/fixtures/llm/<agent>/` recorded request/response pairs (provider-agnostic).
- A factory library (factory-boy) for DB entities, always channel-scoped.
- No real personal data. Voice fixtures are synthetic (TTS) and marked as such.

## 5. Definition of Done (per task) — mirrored in CLAUDE.md
Code + tests (new and existing passing) + docs updated (spec and PROJECT_PROGRESS) + ADR if a decision was made + free-tier check + no new lint or type errors + security checks green.

## 6. Defect handling
- Failing tests are **never skipped silently**. A temporary `xfail` needs an issue link and owner awareness in the phase report.
- Severity: S1 (safety/compliance: e.g. upload without approval, paid call) → stop the phase and fix immediately; S2 (feature broken); S3 (cosmetic).
- A regression test is added for every fixed bug.

## 7. Phase acceptance reporting template
```
## Phase N report — <date>
1. Modules implemented  2. Files created/modified  3. Database changes (migrations)
4. APIs implemented  5. Agents created  6. Tests executed + results (counts, failures, coverage)
7. Free-tier services used  8. Resource consumption (RAM idle/peak, disk, quota, provider usage)
9. Known limitations  10. Remaining tasks  11. Demo script result
```
