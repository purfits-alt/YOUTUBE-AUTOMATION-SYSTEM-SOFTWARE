# ADR-0008: Text-to-speech: owner voice first, then Kokoro / Piper with per-voice licence gate

**Status:** Proposed (pending owner approval at C2) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Verified 2026-11-08: Kokoro-82M is Apache-2.0 (EN/ES/FR, no DE/UR). Piper voice licences vary per voice (CC0, CC-BY, CC BY-NC-SA, MIT). Many EN Piper voices are fine-tuned from lessac (dataset licence needs review). Urdu Piper voices model card says MIT. The Piper engine repo is GPL-3.0.

## Options considered
1. Owner voice + Kokoro + Piper (chosen)
2. Gemini TTS free tier only
3. Paid TTS

## Decision
Priority: owner recording → Kokoro (EN/ES/FR) → Piper (DE: thorsten CC0; UR: fasih/aegis after owner check). Every voice is a registry entry with licence, lineage and commercial flag. NC voices are blocked for monetised channels. The Piper engine runs as a separate process (no linking). Gemini TTS free tier is an optional, disabled-by-default fallback (data-use label).

## Free-tier status
Free. ✔

## Licences
Apache-2.0 (Kokoro), per-voice (Piper), GPL-3.0 engine as separate process.

## Consequences
- German and Urdu quality is lower than English. Owner voice recommended.
- Voice cloning only of the owner's own voice, with a consent record.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
