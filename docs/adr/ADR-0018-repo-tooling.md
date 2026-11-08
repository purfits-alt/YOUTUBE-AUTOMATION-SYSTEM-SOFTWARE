# ADR-0018: Monorepo layout and tooling

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
The brief asks for apps/web, apps/api, workers/, packages/shared, infra/.

## Options considered
1. uv + pnpm monorepo (chosen)
2. Poetry + npm

## Decision
Layout: `apps/api` (FastAPI), `apps/web` (Vite React), `workers/` (agent and media workers), `packages/shared` (JSON schemas, generated TS client), `infra/` (compose, Windows scripts), `docs/`. Python via **uv** (fast, lockfile, manages Python on Windows). JS via **pnpm**. ruff + mypy --strict, eslint + prettier + tsc strict, pre-commit (ruff, eslint, gitleaks).

## Free-tier status
Free. ✔

## Licences
MIT/Apache.

## Consequences
- Single repo, single CI pipeline.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
