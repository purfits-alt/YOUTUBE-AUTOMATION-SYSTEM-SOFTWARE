"""Dependency licence gate (COST_CONTROL_SPEC §7, COMPLIANCE_CHECKLIST E).

Reads `pip-licenses --format=json` output (Python) and/or `pnpm licenses list --json`
output (web) and fails on licences that are not acceptable for this project:
network-copyleft (AGPL, SSPL), source-available/non-commercial (BUSL, RSAL, Commons
Clause, CC-*-NC) or unknown licences that have not been reviewed.

Usage:
  uv run pip-licenses --format=json > py.json
  pnpm -C apps/web licenses list --json --prod > web.json   (optional)
  python tools/check_licenses.py --python py.json [--web web.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DENY = re.compile(
    r"AGPL|Affero|SSPL|Server Side Public|BUSL|Business Source|RSAL|Commons Clause"
    r"|\bNC\b|NonCommercial|Non-Commercial",
    re.I,
)
UNKNOWN = re.compile(r"^(UNKNOWN|)$", re.I)

# Reviewed packages whose metadata does not state a licence clearly. Each entry needs a reason.
REVIEWED: dict[str, str] = {
    "tubeforge": "this project",
}


def check_python(entries: list[dict[str, str]]) -> list[str]:
    problems = []
    for e in entries:
        name, lic = e.get("Name", ""), e.get("License", "")
        if name.lower() in REVIEWED:
            continue
        if DENY.search(lic):
            problems.append(f"python: {name} has a disallowed licence: {lic}")
        elif UNKNOWN.match(lic.strip()):
            problems.append(f"python: {name} has an unknown licence (review and add to REVIEWED)")
    return problems


def check_web(data: dict[str, list[dict[str, object]]]) -> list[str]:
    problems = []
    for lic, packages in data.items():
        if DENY.search(lic) or UNKNOWN.match(lic.strip()):
            names = ", ".join(str(p.get("name")) for p in packages)
            problems.append(f"web: disallowed/unknown licence {lic!r}: {names}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path)
    parser.add_argument("--web", type=Path)
    args = parser.parse_args(argv)
    problems: list[str] = []
    if args.python:
        problems += check_python(json.loads(args.python.read_text(encoding="utf-8")))
    if args.web:
        problems += check_web(json.loads(args.web.read_text(encoding="utf-8")))
    for p in problems:
        print(p)
    print("Licence check passed." if not problems else f"{len(problems)} licence problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
