# ADR-0013: Owner authentication: local accounts, Argon2id, optional TOTP

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Localhost-only single owner. RBAC tables exist for future roles.

## Options considered
1. Local auth (chosen)
2. Self-hosted IdP (Keycloak etc.)

## Decision
argon2-cffi (Argon2id), pyotp TOTP, server-side sessions in Postgres, HttpOnly + SameSite=Strict cookies, CSRF token, lockout after 5 failures in 15 min. Server binds to 127.0.0.1.

## Free-tier status
Free. ✔

## Licences
MIT (argon2-cffi, pyotp).

## Consequences
- An IdP would cost ~1 GB+ RAM, so it was rejected.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
