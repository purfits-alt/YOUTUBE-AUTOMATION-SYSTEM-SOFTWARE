# ADR-0022: Project licence — MIT

**Status:** Accepted (owner decision, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner

## Context
The repository is public but had no licence (open question in the Phase 1 report). Without one, nobody else may legally reuse the code.

## Options considered
1. **MIT** (chosen): short, permissive; reuse allowed with the copyright notice kept.
2. AGPL-3.0: reuse allowed only if changes are shared, including for network use.
3. No licence ("all rights reserved"): others may read but not reuse.

## Decision
TubeForge's own code and documentation are licensed under **MIT** (`LICENSE` at the repo root; `license = "MIT"` in `pyproject.toml` and `apps/web/package.json`).

## Free-tier status
Free. Introduces no paid dependency ✔

## Licences
- MIT applies only to TubeForge's own code. Third-party dependencies, models, voices, fonts and stock media keep their own licences and are still checked by the licence gate (`tools/check_licenses.py`) and the rights records (ADR-0008, ADR-0020).
- The licence gate's deny list (AGPL, SSPL, BUSL, non-commercial, …) is unchanged; those licences would conflict with redistributing TubeForge under MIT.
- FFmpeg remains an external program, not linked (ADR-0011).

## Consequences
- Anyone may reuse, modify and redistribute TubeForge, including commercially, if they keep the copyright notice.
- The owner keeps the copyright.

## References
- `LICENSE`
- `docs/COMPLIANCE_CHECKLIST.md`
