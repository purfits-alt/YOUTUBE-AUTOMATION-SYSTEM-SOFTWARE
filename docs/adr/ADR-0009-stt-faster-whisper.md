# ADR-0009: Speech-to-text and captions: faster-whisper (local)

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Captions are needed in 5 languages. CPU only.

## Options considered
1. faster-whisper (CTranslate2, int8)
2. whisper.cpp
3. Groq Whisper free tier

## Decision
faster-whisper `small` int8 locally. Captions are produced by aligning the known script text, with transcription as a fallback. Groq Whisper free tier is an optional fallback. Urdu captions always need owner review.

## Free-tier status
Free. ✔

## Licences
MIT (faster-whisper, Whisper weights). Re-check in Phase 8.

## Consequences
- ~1 GB RAM while running. One heavy job at a time.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
