"""Traceability check (docs/TRACEABILITY_MATRIX.md).

Verifies that the planning set stays complete and internally consistent:
  * every document required by the master prompt (§18) exists, plus CLAUDE.md;
  * every `docs/...md` path and every bare spec name (e.g. AUDIT_AND_POLICY_SPEC) in the
    matrix points to an existing file;
  * every user story ID (US-x.y) in the matrix exists in PRODUCT_REQUIREMENTS.md;
  * every ADR number referenced anywhere in docs/ exists in docs/adr/;
  * every roadmap phase has a free-tier check line.

Exit code 0 = OK, 1 = problems found (printed one per line).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

REQUIRED_DOCS = [
    "00_MASTER_PROMPT", "PRODUCT_REQUIREMENTS", "SYSTEM_ARCHITECTURE", "TECH_STACK_EVALUATION",
    "FRONTEND_SPECIFICATION", "BACKEND_SPECIFICATION", "DATABASE_SCHEMA", "AI_AGENT_ARCHITECTURE",
    "AGENT_PROMPTS", "CHANNEL_DISCOVERY_SPEC", "VIDEO_PRODUCTION_SPEC", "THUMBNAIL_SEO_SPEC",
    "YOUTUBE_API_INTEGRATION", "OAUTH_SECURITY", "WORKFLOW_STATE_MACHINE", "NOTIFICATION_SPEC",
    "AUDIT_AND_POLICY_SPEC", "FREE_TIER_PROVIDER_MATRIX", "COST_CONTROL_SPEC", "DEPLOYMENT_GUIDE",
    "TESTING_AND_QA", "IMPLEMENTATION_ROADMAP", "CLAUDE_CODE_BUILD_INSTRUCTIONS", "RISK_REGISTER",
    "COMPLIANCE_CHECKLIST", "GLOSSARY", "TRACEABILITY_MATRIX", "PROJECT_PROGRESS",
]  # fmt: skip


def check(root: Path = ROOT) -> list[str]:
    docs = root / "docs"
    problems: list[str] = []

    for name in REQUIRED_DOCS:
        if not (docs / f"{name}.md").is_file():
            problems.append(f"missing required document docs/{name}.md")
    if not (root / "CLAUDE.md").is_file():
        problems.append("missing CLAUDE.md at repository root")

    matrix_path = docs / "TRACEABILITY_MATRIX.md"
    matrix = matrix_path.read_text(encoding="utf-8") if matrix_path.is_file() else ""
    for rel in sorted(set(re.findall(r"\bdocs/[A-Za-z0-9_./-]+\.md\b", matrix))):
        if not (root / rel).is_file():
            problems.append(f"matrix references missing file {rel}")
    spec_name = re.compile(r"\b([A-Z][A-Z_]{5,}(?:SPEC|SPECIFICATION|SCHEMA|INTEGRATION|MATRIX))\b")
    for spec in sorted(set(spec_name.findall(matrix))):
        if not (docs / f"{spec}.md").is_file():
            problems.append(f"matrix references unknown document {spec}")

    prd_path = docs / "PRODUCT_REQUIREMENTS.md"
    prd = prd_path.read_text(encoding="utf-8") if prd_path.is_file() else ""
    for story in sorted(set(re.findall(r"\bUS-\d+\.\d+\b", matrix))):
        if f"**{story}" not in prd:
            problems.append(f"matrix references {story}, which is not defined in PRODUCT_REQUIREMENTS.md")

    adr_dir = docs / "adr"
    existing_adrs = {p.name[4:8] for p in adr_dir.glob("ADR-*.md")} if adr_dir.is_dir() else set()
    referenced: set[str] = set()
    for md in docs.rglob("*.md"):
        if md.name == "00_MASTER_PROMPT.md":
            continue
        referenced |= set(re.findall(r"\bADR-(\d{4})\b", md.read_text(encoding="utf-8")))
    for number in sorted(referenced - existing_adrs):
        problems.append(f"ADR-{number} is referenced but docs/adr/ADR-{number}-*.md does not exist")

    roadmap_path = docs / "IMPLEMENTATION_ROADMAP.md"
    roadmap = roadmap_path.read_text(encoding="utf-8") if roadmap_path.is_file() else ""
    phases = re.findall(r"^## Phase (\d+) — ", roadmap, re.M)
    free_check = re.compile(r"^\*\*Free-tier check:\*\* This phase introduces no paid dependency: ✔", re.M)
    free_checks = free_check.findall(roadmap)
    if len(phases) != 16:
        problems.append(f"roadmap should define 16 phases, found {len(phases)}")
    if len(free_checks) != len(phases):
        problems.append(f"roadmap: {len(phases)} phases but {len(free_checks)} free-tier checks")

    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(f"TRACEABILITY: {p}")
    if not problems:
        print("Traceability check passed.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
