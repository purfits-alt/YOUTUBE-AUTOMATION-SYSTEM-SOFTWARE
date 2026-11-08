"""Contract tests (BACKEND_SPECIFICATION §6): property-based requests against the committed OpenAPI.

Every GET endpoint is called (signed in as the owner) with generated parameters; responses must use
documented status codes, content types and schemas, and never be a server error. Writes are covered
by the targeted tests (idempotency, audit-row-per-write) because random writes would trigger lockout
and Emergency Stop.
"""

from __future__ import annotations

from typing import Any

import pytest
import schemathesis
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, settings

from tests.integration.conftest import BASE_URL, Env, login
from tubeforge.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def owner_cookies(env: Env) -> dict[str, str]:
    with env.client() as c:
        login(c)
        return {"tf_session": c.cookies["tf_session"], "tf_csrf": c.cookies["tf_csrf"]}


@pytest.fixture
def api_schema(env: Env) -> Any:
    app = create_app(env.app_settings)
    return (
        # Host header: our DNS-rebinding guard only accepts loopback host:port.
        schemathesis.openapi.from_asgi("/api/openapi.json", app, headers={"host": "127.0.0.1:8765"})
        # include() ORs the filters given in one call, so chain them to AND them.
        .include(method="GET")
        .include(path_regex="^/api/v1/")
        .exclude(path="/api/v1/events/stream")  # infinite stream; covered by test_controls_api
    )


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@settings(max_examples=10, deadline=None, suppress_health_check=list(HealthCheck))
def test_get_endpoints_match_the_contract(case: Any, owner_cookies: dict[str, str]) -> None:
    case.call_and_validate(base_url=BASE_URL, cookies=owner_cookies)


def test_openapi_documents_problem_responses(env: Env) -> None:
    spec = TestClient(create_app(env.app_settings), base_url=BASE_URL).get("/api/openapi.json").json()
    for path, ops in spec["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method, op in ops.items():
            assert {"401", "403"} <= set(op["responses"]), f"{method.upper()} {path}"
