# ADR-0002: Backend: Python FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
We need typed REST contracts, async I/O for uploads and SSE, low RAM, and Python for the AI and media tooling.

## Options considered
1. FastAPI + SQLAlchemy 2 + Alembic
2. Django + DRF
3. Litestar

## Decision
FastAPI with Pydantic v2 models as the single source of truth for API schemas. SQLAlchemy 2.0 (typed ORM) and Alembic migrations. The OpenAPI document generates the TypeScript client.

## Free-tier status
Free. ✔

## Licences
MIT (FastAPI, SQLAlchemy, Alembic, Pydantic).

## Consequences
- We implement auth and admin ourselves (small scope).
- Async throughout. Blocking media work runs in workers, never in the API process.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
