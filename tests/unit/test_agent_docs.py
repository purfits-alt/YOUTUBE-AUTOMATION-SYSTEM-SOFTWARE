"""agents/ job descriptions are generated from AI_AGENT_ARCHITECTURE §4 and must stay current."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = [
    "## Agent Role",
    "## Actions",
    "## TubeForge Instructions",
    "## Mission",
    "## Context",
    "## Input",
    "## Responsibilities",
    "## Process",
    "## Output",
    "## Handoff Instructions",
    "## Constraints — Security & Misuse Guardrails",
]


def _generator():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("gen_agent_docs", ROOT / "tools" / "gen_agent_docs.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_docs_are_current_and_complete() -> None:
    expected = _generator().expected_files()
    on_disk = {p for p in (ROOT / "agents").glob("*.md")}
    assert on_disk == set(expected), "run: uv run python tools/gen_agent_docs.py"
    for path, content in expected.items():
        assert path.read_text(encoding="utf-8") == content, (
            f"{path.name} is stale: run tools/gen_agent_docs.py"
        )
    agents = [p for p in expected if p.name != "README.md"]
    assert len(agents) == 32
    for path in agents:
        text = expected[path]
        positions = [text.index(s) for s in SECTIONS]
        assert positions == sorted(positions), path.name
        assert "## Process\n1. " in text and "## Handoff Instructions\n\n" not in text
