# ADR-0010: Visuals: non-generative by default; generative image adapter disabled

**Status:** Proposed (pending owner approval at C2) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Verified 2026-11-08: Gemini image models are not on the free tier. Local diffusion is not feasible on H-LITE. Some open models are non-commercial.

## Options considered
1. Procedural/owner/CC0 visuals (chosen)
2. Free-tier cloud image API
3. Local diffusion

## Decision
Default visual styles: motion graphics, kinetic typography, charts and data visualisation, Ken Burns on owner or CC0 photos, owner footage. An `ImageGenerator` adapter interface exists. Implementations are disabled until a free provider passes licence (commercial use) and free-tier verification in a Phase 8 spike.

## Free-tier status
Free. ✔

## Licences
Pillow (HPND), matplotlib (PSF-style), CC0 assets with rights records.

## Consequences
- Fully licensed output with low copyright risk.
- Visual variety must come from templates *plus* owner media, to avoid the 'template' look (F3).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
