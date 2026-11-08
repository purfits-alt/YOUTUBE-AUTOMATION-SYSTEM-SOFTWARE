"""OAUTH_SECURITY §3: "A CI test asserts that every route declares a permission"."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from tubeforge.api.deps import Require, authenticated, pre_mfa, public
from tubeforge.config import Settings
from tubeforge.main import create_app

MARKERS = {public, authenticated, pre_mfa}


def _rule_of(call: Any) -> str | None:
    if isinstance(call, Require):
        return f"require:{call.permission}"
    if call in MARKERS:
        return str(call.__name__)
    return None


def _access_rules(dependant: Dependant) -> list[str]:
    found = [rule] if (rule := _rule_of(dependant.call)) else []
    for sub in dependant.dependencies:
        found.extend(_access_rules(sub))
    return found


def api_routes(app: FastAPI) -> Iterator[tuple[str, APIRoute, list[str]]]:
    """(full path, route, rules from router-level dependencies). FastAPI 0.162 keeps included
    routers as wrappers, so walk them instead of reading app.routes flat."""

    def walk(
        routes: list[Any], prefix: str, inherited: list[str]
    ) -> Iterator[tuple[str, APIRoute, list[str]]]:
        for route in routes:
            if isinstance(route, APIRoute):
                yield prefix + route.path, route, inherited
            elif hasattr(route, "original_router"):
                ctx = route.include_context
                extra = [r for d in ctx.dependencies if (r := _rule_of(d.dependency))]
                yield from walk(route.original_router.routes, prefix + ctx.prefix, inherited + extra)

    yield from walk(list(app.routes), "", [])


def test_every_api_route_declares_an_access_rule(settings: Settings) -> None:
    routes = [(p, r, inh) for p, r, inh in api_routes(create_app(settings)) if p.startswith("/api/v1")]
    assert len(routes) >= 10, "API routes not found"
    missing = [f"{sorted(r.methods)} {p}" for p, r, inh in routes if not (_access_rules(r.dependant) or inh)]
    assert missing == [], f"routes without public/authenticated/require(...): {missing}"


def test_only_login_is_public(settings: Settings) -> None:
    public_routes = [
        p for p, r, inh in api_routes(create_app(settings)) if "public" in _access_rules(r.dependant) + inh
    ]
    assert public_routes == ["/api/v1/auth/login", "/oauth/callback"]
