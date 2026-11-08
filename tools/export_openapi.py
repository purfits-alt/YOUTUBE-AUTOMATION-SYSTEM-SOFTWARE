"""Write the API contract snapshot: packages/shared/openapi.json (BACKEND_SPECIFICATION §1 "Versioning").

The web client's TypeScript types are generated from this file (pnpm -C apps/web api:gen), and a test
fails when the committed snapshot differs from the running code, so contract changes are reviewed.

  uv run python tools/export_openapi.py          # write
  uv run python tools/export_openapi.py --check  # CI
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packages" / "shared" / "openapi.json"


def build() -> str:
    from tubeforge.config import Settings
    from tubeforge.main import create_app

    spec: dict[str, Any] = create_app(Settings(env="test", web_dist_dir=ROOT / "no-web")).openapi()
    spec["info"]["version"] = "v1"  # the package version must not churn the contract
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = build()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            print("packages/shared/openapi.json is stale: run 'uv run python tools/export_openapi.py'")
            return 1
        print("OpenAPI snapshot is up to date.")
        return 0
    OUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
