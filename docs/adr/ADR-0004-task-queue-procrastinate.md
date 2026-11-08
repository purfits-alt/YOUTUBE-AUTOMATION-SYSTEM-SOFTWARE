# ADR-0004: Task queue: Procrastinate (PostgreSQL-backed)

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
A separate Redis/Valkey broker costs RAM. Redis 8+ is tri-licensed RSALv2/SSPLv1/AGPLv3 (verified 2026-11-08). Jobs must be enqueued in the same transaction as the state change.

## Options considered
1. Procrastinate (MIT)
2. Celery + Valkey (BSD)
3. Dramatiq + Valkey
4. Custom SKIP LOCKED queue

## Decision
Procrastinate behind our own `JobQueue` interface. Fallback: a custom `FOR UPDATE SKIP LOCKED` implementation of the same interface, used if the Phase 1 Windows spike fails.

## Free-tier status
Free. ✔ No extra server.

## Licences
MIT (verified: procrastinate LICENSE.md, 2026-11-08).

## Consequences
- Transactional enqueue gives exactly-once state change + job creation.
- Phase 1 must include a Windows CI smoke test of the worker.
- Throughput is far above our needs (tens of jobs/hour).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`

## Phase 1 spike result (2026-11-08)
- **Linux:** Procrastinate 3.10 works: schema applied through Alembic (0001), jobs enqueued and executed by both worker profiles (`light`, `heavy`), and the queueing lock blocks a duplicate waiting job. Tests: `tests/integration/test_db_and_queue.py`.
- Implementation notes: a Procrastinate `Blueprint` is modified when it is attached to an app, so tasks come from a `make_blueprint()` factory. The schema SQL is executed with `%` escaped for psycopg.
- **Windows:** the same tests run on `windows-latest` in CI with `WindowsSelectorEventLoopPolicy`. The fallback SKIP LOCKED queue is only needed if that job fails (see PROJECT_PROGRESS Phase 1 report).
