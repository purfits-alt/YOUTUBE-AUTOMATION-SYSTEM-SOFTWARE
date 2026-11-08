"""FastAPI application factory.

Phase 1 scope: health/readiness endpoints, Host-header guard (DNS-rebinding defence,
OAUTH_SECURITY §2), and serving the built web app. Auth, RBAC, CSRF and the v1 API
arrive in Phase 3.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import Scope

from tubeforge.api.errors import STANDARD_RESPONSES, install_error_handlers, problem_response
from tubeforge.api.v1 import auth as auth_v1
from tubeforge.api.v1 import events as events_v1
from tubeforge.api.v1 import security as security_v1
from tubeforge.api.v1 import system as system_v1
from tubeforge.config import Settings, get_settings
from tubeforge.db.session import check_database, get_engine, table_exists
from tubeforge.events import EventBus
from tubeforge.logging import configure_logging, get_logger
from tubeforge.secrets import MasterKeyMissingError, SecretBox, SecretsError, default_store

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


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request id (echoed as X-Request-ID) and Origin check (OAUTH_SECURITY §2: blocks other sites)."""

    def __init__(self, app: Any, allowed_origins: frozenset[str]) -> None:
        super().__init__(app)
        self._origins = allowed_origins

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4()
        origin = request.headers.get("origin")
        if origin is not None and origin not in self._origins:
            response: Response = problem_response(
                request,
                403,
                "ORIGIN_REJECTED",
                "Request blocked",
                "Requests must come from TubeForge itself.",
            )
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response


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


# Paths that must never fall back to the SPA's index.html (they belong to the API).
API_PREFIXES = ("/api/", "/healthz", "/readyz")


class SPAStaticFiles(StaticFiles):
    """Serve the built web app; unknown non-file paths (client-side routes) get index.html."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            request_path: str = scope.get("path", "")
            last_segment = request_path.rsplit("/", 1)[-1]
            if exc.status_code != 404 or request_path.startswith(API_PREFIXES) or "." in last_segment:
                raise
            return await super().get_response("index.html", scope)


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
        responses=STANDARD_RESPONSES,
    )
    origins = frozenset(f"http://{host}" for host in settings.allowed_hosts) | (
        frozenset({"http://127.0.0.1:5173", "http://localhost:5173"})
        if settings.env == "dev"
        else frozenset()
    )
    app.add_middleware(RequestContextMiddleware, allowed_origins=origins)
    app.add_middleware(HostGuardMiddleware, allowed_hosts=settings.allowed_hosts)
    install_error_handlers(app)

    app.state.settings = settings
    app.state.session_factory = sessionmaker(bind=get_engine(settings.database_url), expire_on_commit=False)
    box = SecretBox(default_store(settings.env))
    app.state.secret_box = box
    try:
        app.state.cookie_key = box.derive_key("session-cookie")
    except (MasterKeyMissingError, SecretsError) as exc:
        # Health endpoints still work; auth answers 503 until 'tubeforge-admin init-keys' has run.
        app.state.cookie_key = None
        log.warning("secrets.master_key_unavailable", error=type(exc).__name__)

    app.include_router(auth_v1.router, prefix="/api/v1")
    app.include_router(security_v1.router, prefix="/api/v1")
    app.include_router(system_v1.router, prefix="/api/v1")
    app.include_router(events_v1.router, prefix="/api/v1")
    app.state.events = EventBus()
    app.state.sse_idle_limit_s = None

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": app_version()}

    @app.get("/readyz", tags=["system"], response_model=None)
    def readyz() -> JSONResponse:
        db_ok, db_detail = check_database(settings.database_url)
        queue_ok = db_ok and table_exists(settings.database_url, "procrastinate_jobs")
        data_ok, data_detail = data_dir_writable(settings.resolved_data_dir)
        key_ok = box.keystore_ok()
        checks: dict[str, dict[str, Any]] = {
            "keyring": {"ok": key_ok, "detail": "ok" if key_ok else "run 'tubeforge-admin init-keys'"},
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
        app.mount("/", SPAStaticFiles(directory=settings.web_dist_dir, html=True), name="web")
    else:

        @app.get("/", include_in_schema=False)
        def placeholder() -> HTMLResponse:
            return HTMLResponse(PLACEHOLDER_HTML)

    log.info("api.created", env=settings.env, host=settings.host, port=settings.port)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory``."""
    return create_app()
