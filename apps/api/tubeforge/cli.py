"""Command-line entry points: ``tubeforge-api`` and ``tubeforge-db``."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from tubeforge.config import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def run_api(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tubeforge-api")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev only)")
    args = parser.parse_args(argv)
    settings = get_settings()
    uvicorn.run(
        "tubeforge.main:app_factory",
        factory=True,
        host=settings.host,  # validated loopback-only
        port=settings.port,
        reload=args.reload,
        log_config=None,
        proxy_headers=False,
        server_header=False,
    )


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent / "migrations"))
    return cfg


def db_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tubeforge-db")
    sub = parser.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("upgrade")
    up.add_argument("revision", nargs="?", default="head")
    down = sub.add_parser("downgrade")
    down.add_argument("revision")
    sub.add_parser("current")
    args = parser.parse_args(argv)
    cfg = alembic_config()
    if args.cmd == "upgrade":
        command.upgrade(cfg, args.revision)
    elif args.cmd == "downgrade":
        command.downgrade(cfg, args.revision)
    else:
        command.current(cfg, verbose=True)
