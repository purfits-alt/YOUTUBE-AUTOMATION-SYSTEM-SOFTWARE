"""Generate the PostgreSQL DDL for the TubeForge schema from docs/DATABASE_SCHEMA.md.

The approved schema document is the single source of truth (DATABASE_SCHEMA "must match this
document exactly"). Its SQL blocks use a few readable shorthands; this tool turns them into
real DDL:

- ``id uuid PK`` / ``bigserial PK``          -> ``PRIMARY KEY``
- bare ``created_at`` / ``updated_at`` / ``deleted_at`` items -> full ``timestamptz`` columns
- ``-- enum <name>`` comments              -> ``CHECK (col IN (...))`` from packages/shared/enums.json
- inline ``REFERENCES <table>``            -> ``ALTER TABLE ... ADD FOREIGN KEY`` after all tables
  (the document has forward references, e.g. channel_strategies -> agent_runs)
- the user_roles COALESCE "primary key"     -> a unique expression index (as the doc notes)
- tables with ``updated_at``               -> ``set_updated_at`` trigger
- ``(AO)`` append-only tables              -> trigger that rejects UPDATE and DELETE

Usage:
  uv run python tools/gen_schema_sql.py          # writes apps/api/tubeforge/db/schema_v1.sql
  uv run python tools/gen_schema_sql.py --check  # CI: fail if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "DATABASE_SCHEMA.md"
ENUMS = ROOT / "packages" / "shared" / "enums.json"
OUT = ROOT / "apps" / "api" / "tubeforge" / "db" / "schema_v1.sql"

SHORTHAND = {
    "created_at": "created_at timestamptz NOT NULL DEFAULT now()",
    "updated_at": "updated_at timestamptz NOT NULL DEFAULT now()",
    "deleted_at": "deleted_at timestamptz NULL",
}
# user_roles: PRIMARY KEY (user_id, role_id, COALESCE(channel_id, ...)) is not valid SQL; it becomes a
# unique expression index, so the two plain key columns must stay NOT NULL explicitly.
NOT_NULL_FROM_PK = {"user_roles": {"user_id", "role_id"}}
REF_RE = re.compile(r"\s+REFERENCES\s+(\w+)(?:\s*\((\w+)\))?")
ENUM_COMMENT_RE = re.compile(r"^(.*?)--\s*enum\s+(\w+)", re.IGNORECASE)
TEXT_COLUMN_RE = re.compile(r"(\w+)\s+text\b", re.IGNORECASE)


def enum_column(line: str) -> tuple[str, str] | None:
    """``-- enum X`` names the enum of the *last* text column before the comment on that line
    (a line can declare several, e.g. ``label text NOT NULL, state text NOT NULL, -- enum …``)."""
    m = ENUM_COMMENT_RE.match(line)
    if not m:
        return None
    columns = TEXT_COLUMN_RE.findall(m.group(1))
    return (columns[-1], m.group(2)) if columns else None


@dataclass
class Table:
    name: str
    items: list[str] = field(default_factory=list)
    has_updated_at: bool = False
    append_only: bool = False


@dataclass
class Schema:
    tables: list[Table] = field(default_factory=list)
    foreign_keys: list[tuple[str, str, str, str]] = field(default_factory=list)  # table, col, ref, refcol
    indexes: list[str] = field(default_factory=list)


def sql_blocks(markdown: str) -> list[str]:
    return re.findall(r"```sql\n(.*?)```", markdown, re.DOTALL)


def split_top_level(body: str) -> list[str]:
    """Split a column list on top-level commas (not inside parentheses or '...' string literals)."""
    items, depth, current, quoted = [], 0, [], False
    for ch in body:
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quoted:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [" ".join(i.split()) for i in items if i.strip()]


def table_bodies(block: str) -> list[tuple[str, str, int]]:
    """(name, raw body, start index) of each CREATE TABLE in a block.

    The body ends at the parenthesis that closes the opening one; parentheses and semicolons inside
    ``-- comments`` and ``'strings'`` do not count (a header comment such as
    ``-- API keys (owner's own); never returned`` once cut a table short).
    """
    out = []
    for m in re.finditer(r"CREATE TABLE (\w+)\s*\(", block):
        i, depth, quoted, comment = m.end(), 1, False, False
        while i < len(block) and depth:
            ch = block[i]
            if comment:
                comment = ch != "\n"
            elif quoted:
                quoted = ch != "'"
            elif ch == "-" and block[i : i + 2] == "--":
                comment = True
            elif ch == "'":
                quoted = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        out.append((m.group(1), block[m.end() : i - 1], m.start()))
    return out


def strip_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def parse(markdown: str, enums: dict[str, list[str]]) -> Schema:
    schema = Schema()
    for block in sql_blocks(markdown):
        for name, raw_body, start in table_bodies(block):
            # Per table: two tables in one block can both have a "state" column with different enums.
            enum_cols = dict(found for line in raw_body.splitlines() if (found := enum_column(line)))
            header_line = block[block.rfind("\n", 0, start) + 1 : block.find("\n", start)]
            table = Table(name=name, append_only="(AO)" in header_line)
            for item in split_top_level(strip_comments(raw_body)):
                table.items.extend(convert_item(name, item, enum_cols, enums, schema))
            table.has_updated_at = any(i.startswith("updated_at ") for i in table.items)
            if name in NOT_NULL_FROM_PK:
                # The composite "primary key" became a unique index; keep its plain columns NOT NULL.
                table.items = [
                    f"{i} NOT NULL" if i.split()[0] in NOT_NULL_FROM_PK[name] and "NULL" not in i else i
                    for i in table.items
                ]
            schema.tables.append(table)
        cleaned = strip_comments(block)
        for idx in re.finditer(r"CREATE (UNIQUE )?INDEX[^;]*;", cleaned):
            schema.indexes.append(" ".join(idx.group(0).split()))
    return schema


def convert_item(
    table: str, item: str, enum_cols: dict[str, str], enums: dict[str, list[str]], schema: Schema
) -> list[str]:
    if item in SHORTHAND:
        return [SHORTHAND[item]]
    # A line may hold several shorthands, e.g. "version int NOT NULL DEFAULT 1, created_at" is split
    # already; "created_at timestamptz ..." with a type is kept as written.
    if item.startswith("PRIMARY KEY (") and "COALESCE" in item:
        cols = item[len("PRIMARY KEY (") : -1]
        nil = "'00000000-0000-0000-0000-000000000000'"
        cols = cols.replace(nil, nil + "::uuid")
        schema.indexes.append(f"CREATE UNIQUE INDEX {table}_unique ON {table} ({cols});")
        return []
    item = re.sub(r"\buuid PK\b", "uuid PRIMARY KEY", item)
    item = re.sub(r"\bbigserial PK\b", "bigserial PRIMARY KEY", item)
    ref = REF_RE.search(item)
    if ref and not item.upper().startswith(("PRIMARY KEY", "UNIQUE", "CHECK")):
        column = item.split()[0]
        schema.foreign_keys.append((table, column, ref.group(1), ref.group(2) or ""))
        item = REF_RE.sub("", item)
    column = item.split()[0]
    if column in enum_cols and "CHECK" not in item:
        values = enums[enum_cols[column]]
        item += " CHECK ({} IN ({}))".format(column, ", ".join(f"'{v}'" for v in values))
    return [item]


def render(schema: Schema) -> str:
    out = [
        "-- GENERATED by tools/gen_schema_sql.py from docs/DATABASE_SCHEMA.md — do not edit by hand.",
        "-- Change the document, then run: uv run python tools/gen_schema_sql.py",
        "",
        "CREATE EXTENSION IF NOT EXISTS citext;",
        "",
        "CREATE OR REPLACE FUNCTION tf_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$",
        "BEGIN NEW.updated_at := now(); RETURN NEW; END $$;",
        "",
        "CREATE OR REPLACE FUNCTION tf_append_only() RETURNS trigger LANGUAGE plpgsql AS $$",
        "BEGIN RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME",
        "  USING ERRCODE = 'insufficient_privilege'; END $$;",
        "",
    ]
    for table in schema.tables:
        out.append(f"CREATE TABLE {table.name} (")
        out.append(",\n".join(f"  {i}" for i in table.items))
        out.append(");")
        if table.has_updated_at:
            out.append(
                f"CREATE TRIGGER {table.name}_updated_at BEFORE UPDATE ON {table.name} "
                "FOR EACH ROW EXECUTE FUNCTION tf_set_updated_at();"
            )
        if table.append_only:
            out.append(
                f"CREATE TRIGGER {table.name}_append_only BEFORE UPDATE OR DELETE ON {table.name} "
                "FOR EACH ROW EXECUTE FUNCTION tf_append_only();"
            )
        out.append("")
    for idx in schema.indexes:
        out.append(idx)
    out.append("")
    for table_name, column, ref, refcol in schema.foreign_keys:
        target = f"{ref}({refcol})" if refcol else ref
        out.append(f"ALTER TABLE {table_name} ADD FOREIGN KEY ({column}) REFERENCES {target};")
    out.append("")
    return "\n".join(out)


def table_names(schema: Schema) -> list[str]:
    return [t.name for t in schema.tables]


def build() -> tuple[Schema, str]:
    enums = json.loads(ENUMS.read_text(encoding="utf-8"))["enums"]
    schema = parse(DOC.read_text(encoding="utf-8"), enums)
    return schema, render(schema)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the committed SQL is out of date")
    args = parser.parse_args()
    _, sql = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != sql:
            print(f"{OUT.relative_to(ROOT)} is stale: run 'uv run python tools/gen_schema_sql.py'")
            return 1
        print("Schema SQL is up to date.")
        return 0
    OUT.write_text(sql, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
