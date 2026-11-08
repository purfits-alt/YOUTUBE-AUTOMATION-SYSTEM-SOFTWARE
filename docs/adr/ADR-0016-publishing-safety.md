# ADR-0016: Publishing safety after the 2 Nov 2026 change: explicit privacy, private by default

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Verified 2026-11-08: unverified API projects are no longer restricted to private, and an omitted `privacyStatus` now defaults to **public**.

## Options considered
1. Private by default + explicit privacy (chosen)
2. Public by default

## Decision
(1) The upload client **refuses** to send a `videos.insert` without an explicit `status.privacyStatus` (code invariant + unit test + contract test). (2) Default upload privacy is `private`. (3) Public or scheduled release needs an owner approval record (MANUAL/SEMI) or an owner-approved auto-publish rule (FULLY-AUTO). (4) 'Private-only mode' becomes an owner safety switch (default ON for new channels until the owner has done 3 successful private test uploads). (5) FULLY-AUTO preconditions: N (default 10) successful private test runs + two-step owner activation. The audit requirement is removed because the platform no longer needs it. (6) `containsSyntheticMedia` and `selfDeclaredMadeForKids` must always be set explicitly.

## Free-tier status
Free. ✔

## Licences
—

## Consequences
- Updates PRD (§5 Operating modes, US-9.2, US-9.4) and master prompt F1/F5 assumptions.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
