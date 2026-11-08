# ADR-0007: LLM strategy: Gateway with Gemini free tier → Groq free tier → local Ollama

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
H-LITE cannot run models good enough for multilingual scripts. Verified 2026-11-08: Gemini API free tier exists for Flash/Flash-Lite/2.5 Pro/Gemma 4 models, and **free-tier content is used to improve Google products**. Linking billing moves a project to a paid tier. Groq has a free plan (exact limits per account).

## Options considered
1. Cloud free tiers + local fallback (chosen)
2. Local only
3. Paid API

## Decision
All model calls go through the AI Provider Gateway. Default chain: Gemini free tier (Flash-family) → Groq free plan → Ollama ≤ 3B Q4 local. Hard local limits per provider, task and day. Channels can be flagged local-only, which excludes training-data providers. The Gemini key comes from a Google Cloud project that must never have billing linked (setup guide + startup check warns if a paid-tier header or quota appears).

## Free-tier status
Free tiers only. ✔ Paid models (e.g. Gemini 4 Argon) disabled in the registry.

## Licences
Gemini API terms, Groq terms (owner accepts), Ollama MIT, local model Apache-2.0/MIT (chosen in Phase 5).

## Consequences
- Quality depends on free-tier availability. Limits can change, so the registry has re-verify dates.
- Prompts must not contain secrets or third-party personal data.
- Internet needed for main text generation.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
