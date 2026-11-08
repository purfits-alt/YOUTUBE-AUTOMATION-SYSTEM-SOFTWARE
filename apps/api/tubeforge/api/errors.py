"""RFC 9457 problem+json errors with stable codes (BACKEND_SPECIFICATION §1.1)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from tubeforge.logging import get_logger

log = get_logger("tubeforge.api")


class FieldError(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    code: str
    request_id: str | None = None
    errors: list[FieldError] | None = None


_PROBLEM = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}


def problem_doc(description: str) -> dict[str, Any]:
    """An OpenAPI response entry for a problem+json error (the media type the server really sends)."""
    return {"description": description, "model": Problem, "content": _PROBLEM}


# Documented on every route (BACKEND_SPECIFICATION §1.1), so the OpenAPI contract matches reality.
STANDARD_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: problem_doc("VALIDATION_ERROR (field errors in errors[]) or a bad header"),
    401: problem_doc("UNAUTHENTICATED / MFA_REQUIRED / BAD_CREDENTIALS"),
    403: problem_doc("FORBIDDEN / CSRF_FAILED / REAUTH_REQUIRED / ORIGIN_REJECTED"),
    404: problem_doc("NOT_FOUND"),
    409: problem_doc("State conflict (e.g. IDEMPOTENCY_IN_PROGRESS)"),
    503: problem_doc("NOT_READY (master key or database missing)"),
}


class ProblemError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or title)
        self.status, self.code, self.title, self.detail, self.extra = status, code, title, detail, extra


def unauthenticated(detail: str = "Please sign in.") -> ProblemError:
    return ProblemError(401, "UNAUTHENTICATED", "Not signed in", detail)


def forbidden(detail: str = "You do not have permission for this.") -> ProblemError:
    return ProblemError(403, "FORBIDDEN", "Not allowed", detail)


def not_found(detail: str = "Not found.") -> ProblemError:
    return ProblemError(404, "NOT_FOUND", "Not found", detail)


def problem_response(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None,
    *,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = str(request_id)
    body.update(extra)
    all_headers = dict(headers or {})
    if "retry_after" in extra:
        all_headers["Retry-After"] = str(extra["retry_after"])
    return JSONResponse(
        body, status_code=status, media_type="application/problem+json", headers=all_headers or None
    )


def allowed_methods(app: FastAPI, path: str) -> list[str]:
    """Methods the OpenAPI contract documents for a concrete path (templates like {id} match a segment)."""
    methods: set[str] = set()
    for template, operations in app.openapi().get("paths", {}).items():
        pattern = "^" + re.sub(r"\\{[^/]+\\}", "[^/]+", re.escape(template)) + "$"
        if re.match(pattern, path):
            methods |= {m.upper() for m in operations}
    return sorted(methods)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc.status, exc.code, exc.title, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in e.get("loc", ())[1:]) or "body",
                "message": str(e.get("msg", "")),
            }
            for e in exc.errors()
        ]
        return problem_response(
            request, 400, "VALIDATION_ERROR", "Invalid request", "Some fields are not valid.", errors=errors
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHENTICATED", 403: "FORBIDDEN"}
        headers = dict(exc.headers or {})
        if exc.status_code == 405:
            # Starlette lists only the first matching route's methods; list every documented one.
            allowed = allowed_methods(app, request.url.path)
            if allowed:
                headers["Allow"] = ", ".join(allowed)
        return problem_response(
            request,
            exc.status_code,
            codes.get(exc.status_code, "HTTP_ERROR"),
            str(exc.detail),
            None,
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("api.unhandled", error=type(exc).__name__, path=request.url.path)
        return problem_response(
            request, 500, "INTERNAL", "Something went wrong", "An unexpected error occurred. See the API log."
        )
