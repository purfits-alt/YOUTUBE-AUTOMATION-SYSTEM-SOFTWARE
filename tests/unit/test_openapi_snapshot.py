"""The committed API contract (packages/shared/openapi.json) matches the code."""

from __future__ import annotations

from tools import export_openapi


def test_openapi_snapshot_is_current() -> None:
    assert export_openapi.OUT.read_text(encoding="utf-8") == export_openapi.build(), (
        "API contract changed: run 'uv run python tools/export_openapi.py' and review the diff"
    )
