"""Repository-level checks: planning traceability, shared enums, no forbidden patterns."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tools.check_licenses import check_python, check_web
from tools.check_traceability import ROOT, check


def test_traceability_matrix_is_consistent() -> None:
    assert check() == []


def test_traceability_detects_missing_document(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    problems = check(tmp_path)
    assert any("PRODUCT_REQUIREMENTS" in p for p in problems)
    assert any("CLAUDE.md" in p for p in problems)


def test_shared_enums_match_database_schema_doc() -> None:
    doc = (ROOT / "docs" / "DATABASE_SCHEMA.md").read_text(encoding="utf-8")
    section = doc[doc.index("## 14. Enum value sets") : doc.index("## 15.")]
    from_doc = {
        m.group(1): [v.strip() for v in m.group(2).split(",")]
        for m in re.finditer(r"^\| ([a-z_]+) \| ([A-Z_0-9, ]+) \|$", section, re.M)
    }
    shared = json.loads((ROOT / "packages" / "shared" / "enums.json").read_text(encoding="utf-8"))["enums"]
    assert shared == from_doc
    assert "EXTERNAL_EDITING" in shared["project_state"]  # ADR-0021 state present


def test_licence_gate_blocks_agpl_and_unknown() -> None:
    problems = check_python(
        [
            {"Name": "fastapi", "License": "MIT"},
            {"Name": "psycopg", "License": "GNU Lesser General Public License v3 (LGPLv3)"},
            {"Name": "bad-a", "License": "GNU Affero General Public License v3"},
            {"Name": "bad-b", "License": "UNKNOWN"},
        ]
    )
    assert len(problems) == 2
    assert check_web({"MIT": [{"name": "react"}], "SSPL-1.0": [{"name": "x"}]}) == [
        "web: disallowed/unknown licence 'SSPL-1.0': x"
    ]


def test_no_youtube_html_scraping_targets_in_code() -> None:
    """DP-8: application code must never target YouTube HTML pages (only the official API hosts)."""
    pattern = re.compile(r"https?://(www\.|m\.)?youtube\.com/(watch|results|channel|c/|@|feed)")
    offenders = []
    for folder in ("apps/api/tubeforge", "workers"):
        for path in (ROOT / folder).rglob("*.py"):
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_billing_or_payment_clients() -> None:
    """COST_CONTROL G2/G4: no billing/payment SDKs in dependencies."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    web = (ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8").lower()
    for forbidden in ("google-cloud-billing", "stripe", "paypal", "braintree"):
        assert forbidden not in pyproject
        assert forbidden not in web


def test_every_python_source_file_is_tracked_by_git() -> None:
    """An over-broad .gitignore pattern once hid a whole code package (db/models/) from the repo."""
    import shutil
    import subprocess

    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        return
    ignored = subprocess.run(  # noqa: S603 - fixed argv, git resolved via shutil.which
        [
            git,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            "apps",
            "workers",
            "tools",
            "tests",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    hidden = [f for f in ignored if f.endswith((".py", ".sql", ".ts", ".tsx")) and "node_modules" not in f]
    assert hidden == [], f"source files ignored by .gitignore: {hidden}"


def test_no_billing_api_hosts_in_code() -> None:
    """COST_CONTROL_SPEC G2/G4: no code path can reach a billing, plan or payment API (the test above
    covers dependencies; this one the source)."""
    import re

    root = ROOT
    forbidden = re.compile(
        r"cloudbilling\.googleapis\.com|billingbudgets\.googleapis\.com|api\.stripe\.com|api\.paypal\.com"
        r"|\bimport stripe\b|\bfrom stripe\b|braintree|paddle\.com|checkout\.session",
        re.IGNORECASE,
    )
    for folder in ("apps/api/tubeforge", "workers", "apps/web/src"):
        for path in (root / folder).rglob("*"):
            if path.suffix in {".py", ".ts", ".tsx"} and "node_modules" not in path.parts:
                assert not forbidden.search(path.read_text(encoding="utf-8")), path
