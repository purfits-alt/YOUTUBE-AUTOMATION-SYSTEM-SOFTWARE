# ADR-0011: Video engine: FFmpeg driven by a timeline-JSON compiler

**Status:** Proposed (pending owner approval at C2) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Reproducible renders, low RAM, CPU-only.

## Options considered
1. Own timeline → FFmpeg filter-graph compiler
2. MoviePy
3. Remotion

## Decision
Timeline JSON (versioned schema) is compiled to FFmpeg filter graphs. Proxy (low-res) renders for preview. x264 `veryfast`/`faster` presets on H-LITE. Two-pass loudnorm to the target LUFS. ffprobe QC after every render.

## Free-tier status
Free. ✔

## Licences
FFmpeg LGPL/GPL build (used as an external binary).

## Consequences
- Deterministic and testable (ffprobe assertions).
- We maintain the compiler (scoped to the effects we need).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
