"""FastAPI application factory.

Phase 1 scope: health/readiness endpoints, Host-header guard (DNS-rebinding defence,
OAUTH_SECURITY §2), and serving the built web app. Auth, RBAC, CSRF and the v1 API
arrive in Phase 3.
"""

from __future__ import annotations

import os
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from tubeforge.config import Settings, get_settings
from tubeforge.db.session import check_database, table_exists
from tubeforge.logging import configure_logging, get_logger

PLACEHOLDER_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>TubeForge</title></head>
<body style="font-family:system-ui;margin:2rem"><h1>TubeForge is running</h1>
<p>The web app has not been built yet. Run <code>pnpm -C apps/web build</code>.</p>
<p><a href="/readyz">Readiness checks</a></p></body></html>"""


def app_version() -> str:
    try:
        return version("tubeforge")
    except PackageNotFoundError:
        return "0.0.0+local"


def problem(status: int, title: str, detail: str, code: str, **extra: Any) -> JSONResponse:
    """RFC 9457 problem+json (BACKEND_SPECIFICATION §1)."""
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, "code": code, **extra}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


class HostGuardMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Host header is not a loopback name (blocks DNS rebinding)."""

    def __init__(self, app: Any, allowed_hosts: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed = allowed_hosts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.headers.get("host", "")
        if host not in self._allowed:
            return problem(400, "Bad host", "Requests must target this computer (127.0.0.1).", "BAD_HOST")
        return await call_next(request)


def data_dir_writable(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".tf-probe-", dir=path)
        os.close(fd)
        Path(probe).unlink()
    except OSError as exc:
        return False, type(exc).__name__
    return True, "ok"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("tubeforge.api")

    app = FastAPI(
        title="TubeForge",
        version=app_version(),
        docs_url="/api/docs" if settings.env != "prod" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(HostGuardMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": app_version()}

    @app.get("/readyz", tags=["system"], response_model=None)
    def readyz() -> JSONResponse:
        db_ok, db_detail = check_database(settings.database_url)
        queue_ok = db_ok and table_exists(settings.database_url, "procrastinate_jobs")
        data_ok, data_detail = data_dir_writable(settings.resolved_data_dir)
        checks: dict[str, dict[str, Any]] = {
            "database": {"ok": db_ok, "detail": db_detail},
            "queue_schema": {"ok": queue_ok, "detail": "ok" if queue_ok else "run 'tubeforge-db upgrade'"},
            "data_dir": {"ok": data_ok, "detail": data_detail},
        }
        if all(c["ok"] for c in checks.values()):
            return JSONResponse({"status": "ready", "checks": checks})
        log.warning("readyz.not_ready", checks=checks)
        return problem(
            503, "Not ready", "One or more dependencies are unavailable.", "NOT_READY", checks=checks
        )

    index = settings.web_dist_dir / "index.html"
    if index.is_file():
        app.mount("/", StaticFiles(directory=settings.web_dist_dir, html=True), name="web")
    else:

        @app.get("/", include_in_schema=False)
        def placeholder() -> HTMLResponse:
            return HTMLResponse(PLACEHOLDER_HTML)

    log.info("api.created", env=settings.env, host=settings.host, port=settings.port)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory``."""
    return create_app()
