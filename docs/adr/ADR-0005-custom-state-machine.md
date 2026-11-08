# ADR-0005: Orchestration: custom state machine persisted in PostgreSQL

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Workflows are long-running (hours or days), contain owner-approval gates, and must survive crashes and restarts with a full audit trail.

## Options considered
1. Custom state machine in Postgres
2. LangGraph
3. Temporal

## Decision
Explicit state and transition tables in code (one module per entity: Channel, Idea, VideoProject, RenderJob, UploadJob, Notification). Each transition is one DB transaction: guard check → state write → audit row → next job enqueued. LLM-calling logic lives inside agent tasks, not in the orchestrator.

## Free-tier status
Free. ✔ No extra server (Temporal would need ~1 GB+).

## Licences
Own code.

## Consequences
- Full control over approval gates and audit.
- We must test transitions thoroughly (table-driven tests in Phase 5).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
