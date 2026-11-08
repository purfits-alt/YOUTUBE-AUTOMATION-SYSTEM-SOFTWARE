# ADR-0024: Database DDL generated from DATABASE_SCHEMA.md

**Status:** Accepted (Phase 3, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Claude Code (owner approves with Phase 3)

## Context
DATABASE_SCHEMA.md says the database "must match this document exactly". It defines 78 tables (80 after Phase 3 additions) in readable SQL with shorthands (`created_at`, `uuid PK`, `-- enum x`, forward references). Hand-copying that into migrations and models would drift.

## Options considered
1. **Generate the DDL from the document** (chosen): `tools/gen_schema_sql.py` → `apps/api/tubeforge/db/schema_v1.sql`, applied by migration 0002. A unit test fails if the committed SQL differs from the document.
2. Hand-written Alembic migrations + full SQLAlchemy models for all tables now, plus a `pg_dump` snapshot comparison (the document's original wording).

## Decision
Option 1. SQLAlchemy models are written per phase for the tables that phase uses; an integration test checks every mapped column exists with matching nullability. Gaps found while implementing are fixed **in the document first** (Phase 3 added `idempotency_keys`, `user_recovery_codes`, `sessions.reauth_at`).

Before the first release, migration 0002 still reads the current `schema_v1.sql`. After a release, schema changes go into new numbered migrations (and the document), never by editing 0002.

## Free-tier status
Free. Introduces no paid dependency ✔

## Consequences
- The schema document and the database cannot silently diverge.
- Enum CHECKs come from `packages/shared/enums.json`, shared with the web app.
- Append-only tables (AO) are enforced by a trigger, because the application role owns the tables and cannot be denied UPDATE/DELETE by grants alone.

## References
- `docs/DATABASE_SCHEMA.md`, `tools/gen_schema_sql.py`, `tests/unit/test_schema_and_seeds.py`
