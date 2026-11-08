# Claude Code Build Instructions

**Version:** 1.0 (approved at C6, 2026-11-08) · **Date:** 2026-11-08
How Claude Code (or any developer) builds TubeForge, phase by phase, after C6 approval.

## 1. Starting a phase
The owner sends:
> Implement Phase N from `docs/IMPLEMENTATION_ROADMAP.md`. Follow `CLAUDE.md`. Stop when the phase's acceptance tests pass and show me the results.

Claude Code then:
1. Reads `CLAUDE.md`, the phase section in IMPLEMENTATION_ROADMAP, and the specs it references (only the relevant sections).
2. Writes a short plan (tasks → files → tests) into `PROJECT_PROGRESS.md` under "Phase N — plan".
3. Creates a branch `phase-N-<slug>` from the latest `main` (or the agreed integration branch).
4. Implements in **small commits** (one logical change each, tests included), and runs the relevant tests after each.
5. Runs the full phase test suite plus lint, type and security checks.
6. Writes the **phase report** (TESTING_AND_QA §7) into PROJECT_PROGRESS, pushes, and opens a PR only if the owner asks.
7. **Stops** and asks the owner to run the demo script and reply "approved".

## 2. Source of truth & precedence
1. The owner's latest explicit instruction
2. Approved checkpoint decisions (PROJECT_PROGRESS) and accepted ADRs
3. Specs (PRD → architecture → interface specs → domain specs)
4. Master prompt (`00_MASTER_PROMPT.md`)

If two documents conflict, implement the higher one **and** record the conflict and fix the lower document in the same PR. If a requirement is missing, **do not guess**: add it to "Open questions" in PROJECT_PROGRESS and ask the owner.

## 3. Engineering rules (summary — full list in CLAUDE.md)
- Python: typed (mypy strict), Pydantic v2 models for all I/O, SQLAlchemy 2.0 typed ORM, async where I/O-bound, no blocking calls in the API process.
- TypeScript: strict, generated API client only (no hand-written fetch to `/api`), zod validation for forms.
- Every external call goes through its gateway or adapter (AI Gateway, SafeYouTubeClient, Stock adapter, Notifier, ResearchFetcher). An import-lint rule enforces this.
- Every state change goes through the Orchestrator `transition()` in one DB transaction.
- Every new table goes into an Alembic migration with a downgrade.
- Every new endpoint: permission, idempotency where required, problem+json errors, audit row, contract test.
- Every new agent: input/output JSON Schema, prompt file with version, golden tests, registry row.
- Every new provider: registry row with tier, licence, commercial use, data-use, limits, verified URL and date.
- Secrets never in code, logs, fixtures or commits. Test keys only via CI env.
- Windows compatibility: `pathlib`, quoted paths, argv lists for subprocesses, no `fork`, test on the Windows CI job.

## 4. Verification before claiming "done"
- Run the commands listed in CLAUDE.md "Test commands". Paste the summarised results (counts, failures) into the phase report. Never claim a test passed without running it.
- If a test fails and can't be fixed in scope, report it plainly with the output and leave the phase **not accepted**.
- For UI work, run the Playwright suite and capture screenshots of the key pages for the owner.

## 5. Working with the owner
- Keep the owner's plain-language summary short: what changed, what to click, and what's next.
- Ask before: adding any dependency with a non-permissive licence, any new outbound host, any paid service, any change to approved specs or ADRs, any destructive data operation.
- Never push to `main` directly. Never enable a paid provider. Never perform real uploads except to the **test channel**, and only when the phase demo requires it.
