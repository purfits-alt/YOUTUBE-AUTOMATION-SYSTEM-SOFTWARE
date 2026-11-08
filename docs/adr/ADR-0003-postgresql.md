# ADR-0003: Database: PostgreSQL for all environments

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Needs JSONB, row locking for queues, LISTEN/NOTIFY, partial unique indexes for idempotency.

## Options considered
1. PostgreSQL 16+
2. SQLite
3. MySQL/MariaDB

## Decision
PostgreSQL 16+ in dev, test, CI and prod. No SQLite, because tests must match production queue and lock semantics.

## Free-tier status
Free. ✔

## Licences
PostgreSQL Licence (permissive).

## Consequences
- ~150–250 MB RAM with tuned config (shared_buffers 128 MB).
- Backups via pg_dump (ADR in Phase 15).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
