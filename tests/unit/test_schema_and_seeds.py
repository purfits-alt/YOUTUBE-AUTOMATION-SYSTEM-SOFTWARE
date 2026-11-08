"""The generated schema SQL and the seed migration stay in sync with their sources."""

from __future__ import annotations

import importlib.util
import re
import uuid
from pathlib import Path
from types import ModuleType

from tools import gen_schema_sql
from tubeforge.auth.permissions import PERMISSIONS, ROLE_PERMISSIONS
from tubeforge.db.ids import uuid7

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_schema_sql_matches_the_document() -> None:
    _, sql = gen_schema_sql.build()
    assert gen_schema_sql.OUT.read_text(encoding="utf-8") == sql, "run: uv run python tools/gen_schema_sql.py"


def test_every_documented_table_is_generated() -> None:
    doc = (ROOT / "docs" / "DATABASE_SCHEMA.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"CREATE TABLE (\w+)", doc))
    schema, _ = gen_schema_sql.build()
    assert set(gen_schema_sql.table_names(schema)) == documented
    assert len(documented) == 80


def test_enum_checks_are_per_table() -> None:
    _, sql = gen_schema_sql.build()
    ideas = sql[sql.index("CREATE TABLE video_ideas") : sql.index("CREATE TABLE video_projects")]
    assert "'SUGGESTED'" in ideas and "'RESEARCHING'" not in ideas


def test_seed_migration_matches_permission_module() -> None:
    seed = _load(ROOT / "apps" / "api" / "migrations" / "versions" / "0003_seed_roles_permissions.py")
    assert dict(seed.PERMISSIONS) == PERMISSIONS
    assert {r: frozenset(p) for r, p in seed.ROLE_PERMISSIONS.items()} == ROLE_PERMISSIONS


def test_role_hierarchy() -> None:
    assert ROLE_PERMISSIONS["OWNER"] == frozenset(PERMISSIONS)
    assert ROLE_PERMISSIONS["VIEWER"] < ROLE_PERMISSIONS["REVIEWER"] < ROLE_PERMISSIONS["OWNER"]
    assert ROLE_PERMISSIONS["VIEWER"] < ROLE_PERMISSIONS["EDITOR"] < ROLE_PERMISSIONS["OWNER"]
    owner_only = {
        "emergency.clear",
        "publish.decide",
        "audit.override",
        "channel.mode",
        "providers.paid",
        "security.view",
    }
    for role in ("EDITOR", "REVIEWER", "VIEWER"):
        assert not owner_only & ROLE_PERMISSIONS[role]


def test_uuid7_layout_and_ordering() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert len(set(ids)) == 50
    assert [i.int >> 80 for i in ids] == sorted(i.int >> 80 for i in ids)
