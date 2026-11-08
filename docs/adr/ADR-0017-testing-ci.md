# ADR-0017: Testing and CI: pytest, Vitest, Playwright, GitHub Actions

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Verified 2026-11-08: standard GitHub-hosted runners are free for public repositories.

## Options considered
1. GitHub Actions (chosen)
2. Local-only CI

## Decision
pytest (+ asyncio, httpx, real Postgres service), Vitest + Testing Library, Playwright E2E (Chromium), ffprobe render assertions, schemathesis-style contract tests against OpenAPI. CI matrix: ubuntu-latest (full) + windows-latest (install, queue and render smoke tests). Mocked providers only. GPU and model tests are local only.

## Free-tier status
Free (public repo). ✔ If the repo becomes private, CI minutes become limited, so re-check.

## Licences
—

## Consequences
- The repo must stay public for unlimited free standard runners, or CI is trimmed.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
