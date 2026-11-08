"""RFC 9457 problem+json errors with stable codes (BACKEND_SPECIFICATION §1.1)."""

from __future__ import annotations

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
    request: Request, status: int, code: str, title: str, detail: str | None, **extra: Any
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
    headers = {"Retry-After": str(extra["retry_after"])} if "retry_after" in extra else None
    return JSONResponse(body, status_code=status, media_type="application/problem+json", headers=headers)


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
        return problem_response(
            request, exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail), None
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("api.unhandled", error=type(exc).__name__, path=request.url.path)
        return problem_response(
            request, 500, "INTERNAL", "Something went wrong", "An unexpected error occurred. See the API log."
        )
