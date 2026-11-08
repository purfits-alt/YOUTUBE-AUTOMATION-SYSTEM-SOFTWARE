# ADR-0012: Secrets: AES-256-GCM envelope encryption, master key in Windows Credential Manager

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
OAuth refresh tokens give full channel control. The repo is public.

## Options considered
1. AES-GCM + OS keyring (chosen)
2. Fernet with key in .env
3. Plaintext .env

## Decision
`cryptography` AESGCM with a per-secret data key, wrapped by a master key stored in Windows Credential Manager via `keyring`. CI and Linux use an env-var key for tests only. `.env` holds non-secret config only. gitleaks runs in pre-commit and CI.

## Free-tier status
Free. ✔

## Licences
Apache-2.0/BSD (cryptography), MIT (keyring).

## Consequences
- If the OS keyring is lost, re-authorisation is needed. The backup includes an encrypted key export protected by an owner passphrase.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
