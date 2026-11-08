# ADR-0006: Frontend: Vite + React + TypeScript SPA served by FastAPI

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code · **Amended by ADR-0023** (no shadcn/ui or Recharts in the shell; own components, icons, charts and Lottie)

## Context
Single-user, localhost-only dashboard. A Next.js server would add 150–300 MB of resident RAM for no SSR benefit.

## Options considered
1. Vite + React SPA
2. Next.js
3. SvelteKit

## Decision
Vite + React + TypeScript (strict) + React Router + TanStack Query/Table + Tailwind CSS + shadcn/ui + Recharts. Production build is static and served by FastAPI. Vite dev server in development only.

## Free-tier status
Free. ✔

## Licences
MIT for all listed packages.

## Consequences
- Zero runtime RAM for the UI in production.
- Deviates from the brief's first suggestion (Next.js), with justification above.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
