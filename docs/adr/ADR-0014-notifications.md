# ADR-0014: Notifications: in-app SSE + Telegram; SMTP optional; WhatsApp disabled

**Status:** Proposed (pending owner approval at C2) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Verified 2026-11-08: Telegram bots message users at no cost (≈1 msg/s per chat).

## Options considered
1. In-app + Telegram (chosen)
2. Email-first
3. WhatsApp

## Decision
In-app via Server-Sent Events. Telegram Bot API adapter (token encrypted). SMTP adapter optional. WhatsApp adapter exists as Tier P, disabled, cost shown before enabling. Dedup keys, quiet hours (23:00–08:00 Asia/Karachi, except critical alerts), digests.

## Free-tier status
Free. ✔

## Licences
Telegram Bot API terms.

## Consequences
- The owner must create a Telegram bot (guided in Phase 14).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
