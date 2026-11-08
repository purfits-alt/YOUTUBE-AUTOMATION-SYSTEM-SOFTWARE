# ADR-0001: Native Windows install as the primary deployment

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Owner PC is Windows 10, 8 GB RAM, no GPU (H-LITE). Docker Desktop on WSL2 reserves ~2 GB+ RAM.

## Options considered
1. Native install (PostgreSQL Windows installer, Python via uv, FFmpeg static build, start script)
2. Docker Desktop + Compose
3. WSL2 Linux install without Docker

## Decision
Native Windows install is primary. Docker Compose is used for CI and Linux developers. A PowerShell setup script checks prerequisites (≥ 60 GB free disk, ≥ 8 GB RAM, Windows 10 22H2+) and installs pinned versions.

## Free-tier status
All components free. ✔

## Licences
PostgreSQL licence, PSF/MIT (Python, uv), LGPL/GPL (FFmpeg build, used unmodified and not redistributed).

## Consequences
- Saves ~2 GB RAM.
- Two install paths to document and test (Windows CI job required).
- Windows-specific bugs (paths, event loop) must be covered by tests.

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`

## Amendment (C3, 2026-11-08)
The owner chose the install root **`D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE`**. Program, data, models, PostgreSQL data directory and backups all live there (layout in SYSTEM_ARCHITECTURE §11). Because the path contains spaces, scripts must quote every path and subprocesses use argv lists. The Windows CI job installs into a path with spaces.
