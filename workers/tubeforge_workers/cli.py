"""``tubeforge-worker --queues light|heavy`` — runs a Procrastinate worker profile."""

from __future__ import annotations

import argparse
import asyncio

from tubeforge.config import get_settings
from tubeforge.logging import configure_logging, get_logger
from tubeforge.queue import WORKER_PROFILES, build_app, ensure_windows_event_loop_policy


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tubeforge-worker")
    parser.add_argument("--queues", choices=sorted(WORKER_PROFILES), required=True)
    parser.add_argument(
        "--once",
        action="store_true",
        help="process the jobs currently waiting, then exit (used by smoke tests)",
    )
    return parser.parse_args(argv)


async def run(profile: str, *, once: bool = False) -> None:
    settings = get_settings()
    queues, concurrency = WORKER_PROFILES[profile]
    log = get_logger("tubeforge.worker")
    app = build_app(settings.libpq_dsn)
    async with app.open_async():
        log.info("worker.start", profile=profile, queues=list(queues), concurrency=concurrency, once=once)
        await app.run_worker_async(
            queues=list(queues),
            concurrency=concurrency,
            wait=not once,
            install_signal_handlers=not once,
        )
        log.info("worker.stop", profile=profile)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    ensure_windows_event_loop_policy()
    asyncio.run(run(args.queues, once=args.once))


if __name__ == "__main__":
    main()
