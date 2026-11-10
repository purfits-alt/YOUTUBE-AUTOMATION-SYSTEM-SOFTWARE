"""Agent Control Center + Cost & Usage APIs (BACKEND_SPECIFICATION §4.16–4.17)."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.integration.conftest import OWNER_PASSWORD, Env

pytestmark = pytest.mark.integration
GROQ = "groq:openai/gpt-oss-20b"
PAID = "gemini:gemini-3.1-pro-preview"


def idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def path(code: str) -> str:
    return quote(code, safe="")


def reauth(client: TestClient, headers: dict[str, str]) -> None:
    assert (
        client.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=headers).status_code
        == 204
    )


# ------------------------------------------------------------------------------------------- agents
def test_agents_list_edit_and_guards(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    client, h = owner_client
    agents = {a["agent_code"]: a for a in client.get("/api/v1/agents").json()}
    assert (
        len(agents) == 33 and agents["T00_HELLO"]["runnable"] and not agents["A11_SCRIPTWRITING"]["runnable"]
    )
    hello = agents["T00_HELLO"]
    assert hello["stats_24h"] == {"runs": 0, "success_pct": None, "p50_ms": None, "tokens": 0}

    r = client.patch("/api/v1/agents/T00_HELLO", json={"limits": {"calls_per_day": 2}}, headers=h)
    assert r.status_code == 428
    r = client.patch(
        "/api/v1/agents/T00_HELLO",
        json={"limits": {"calls_per_day": 2}},
        headers={**h, "If-Match": hello["etag"]},
    )
    assert r.status_code == 200 and r.json()["limits"]["calls_per_day"] == 2
    stale = client.patch(
        "/api/v1/agents/T00_HELLO", json={"enabled": False}, headers={**h, "If-Match": hello["etag"]}
    )
    assert stale.status_code == 412
    etag = r.json()["etag"]
    bad = client.patch(
        "/api/v1/agents/T00_HELLO", json={"provider_chain": ["nope:x"]}, headers={**h, "If-Match": etag}
    )
    assert bad.json()["code"] == "UNKNOWN_PROVIDER"
    ok = client.patch(
        "/api/v1/agents/T00_HELLO",
        json={"provider_chain": ["ollama:qwen2.5:1.5b"]},
        headers={**h, "If-Match": etag},
    )
    assert ok.json()["provider_chain"] == ["ollama:qwen2.5:1.5b"]
    auditor = agents["A32_COST_MONITOR"]
    r = client.patch(
        "/api/v1/agents/A32_COST_MONITOR", json={"enabled": False}, headers={**h, "If-Match": auditor["etag"]}
    )
    assert r.status_code == 409 and r.json()["code"] == "AUDITOR_CANNOT_BE_DISABLED"
    assert client.get("/api/v1/agents/T00_HELLO/prompts").json() == ["v1.0"]


def test_test_run_is_queued_and_runs_through_the_worker(
    env: Env, owner_client: tuple[TestClient, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, h = owner_client
    assert (
        client.post("/api/v1/agents/A11_SCRIPTWRITING/run", json={"input": {}}, headers=idem(h)).json()[
            "code"
        ]
        == "NO_HANDLER"
    )
    assert (
        client.post("/api/v1/agents/T00_HELLO/run", json={"input": {"name": ""}}, headers=idem(h)).status_code
        == 400
    )
    r = client.post("/api/v1/agents/T00_HELLO/run", json={"input": {"name": "Ayesha"}}, headers=idem(h))
    assert r.status_code == 202 and r.json()["job_id"]
    engine = create_engine(env.db_url)
    with engine.connect() as conn:
        args = conn.execute(
            text("SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%agent.run'")
        ).scalar_one()
    engine.dispose()
    assert args == {"agent_code": "T00_HELLO", "data": {"name": "Ayesha"}, "idempotent": False}

    # Run the job body as the worker would: no keys and no Ollama here, so every provider is skipped
    # or unreachable → the run is recorded as FAILED with the reasons (nothing is sent anywhere).
    from tubeforge.config import get_settings
    from tubeforge_workers import maintenance

    get_settings.cache_clear()
    assert maintenance.run_agent("T00_HELLO", {"name": "Ayesha"}, idempotent=False) == "FAILED"
    runs = client.get("/api/v1/agent-runs", params={"agent": "T00_HELLO"}).json()["items"]
    assert len(runs) == 1 and runs[0]["status"] == "FAILED" and runs[0]["input"] == {"name": "Ayesha"}
    assert "no API key entered" in runs[0]["error_detail"]
    assert client.get(f"/api/v1/agent-runs/{runs[0]['id']}").json()["error_class"] == "UNAVAILABLE"
    stats = next(a for a in client.get("/api/v1/agents").json() if a["agent_code"] == "T00_HELLO")[
        "stats_24h"
    ]
    assert stats["runs"] == 1 and stats["success_pct"] == 0


# ---------------------------------------------------------------------------------------- providers
def _providers(client: TestClient) -> dict[str, Any]:
    return {p["code"]: p for p in client.get("/api/v1/providers").json()}


def test_provider_keys_limits_and_verification(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    client, h = owner_client
    ps = _providers(client)
    assert ps[GROQ]["has_key"] is False and ps["ollama:qwen2.5:1.5b"]["has_key"] is True
    assert ps["gemini:gemini-3.8-flash"]["data_use_training"] is True
    r = client.put(
        f"/api/v1/providers/{path(GROQ)}/credentials", json={"secret": "gsk_" + "x" * 24}, headers=h
    )
    assert r.status_code == 204
    ps = _providers(client)
    assert ps[GROQ]["has_key"] and ps["groq:openai/gpt-oss-120b"]["has_key"]  # one key per family
    assert "gsk_" not in client.get("/api/v1/providers").text
    assert (
        client.put(
            f"/api/v1/providers/{path('ollama:qwen2.5:1.5b')}/credentials",
            json={"secret": "abcdefghij"},
            headers=h,
        ).status_code
        == 409
    )

    lims = [
        {"metric": "REQUESTS", "period": "DAY", "limit_value": 900},
        {"metric": "TOKENS", "period": "DAY", "limit_value": 180000},
    ]
    r = client.patch(f"/api/v1/providers/{path(GROQ)}", json={"limits": lims, "enabled": True}, headers=h)
    body = r.json()
    assert r.status_code == 200 and {x["limit_value"] for x in body["provider"]["limits"]} == {900, 180000}
    assert "placeholder" not in body["provider"]["published_limits"]
    assert body["warnings"]  # Groq's data use is unknown → local-only channels skip it
    assert (
        client.patch(f"/api/v1/providers/{path(PAID)}", json={"enabled": True}, headers=h).json()["code"]
        == "USE_PAID_ACTIVATION"
    )

    r = client.post(
        f"/api/v1/providers/{path(GROQ)}/verify",
        json={"verified_url": "https://console.groq.com/docs/rate-limits"},
        headers=h,
    )
    assert r.json()["verified_url"].endswith("rate-limits") and r.json()["reverify_due"] is False
    assert client.delete(f"/api/v1/providers/{path(GROQ)}/credentials", headers=h).status_code == 204
    assert _providers(client)[GROQ]["has_key"] is False


def test_paid_activation_via_api_needs_reauth_and_waits(
    owner_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, h = owner_client
    url = f"/api/v1/providers/{path(PAID)}/paid-activation"
    r = client.post(f"{url}/step1", json={"acknowledge_cost": True}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "REAUTH_REQUIRED"
    reauth(client, h)
    r = client.post(f"{url}/step1", json={"acknowledge_cost": True}, headers=h)
    assert r.status_code == 200 and r.json()["confirm_phrase"] == f"ENABLE PAID {PAID}"
    r = client.post(
        f"{url}/step2",
        json={"confirm_phrase": f"ENABLE PAID {PAID}", "monthly_cap_minor": 500},
        headers=idem(h),
    )
    assert r.status_code == 409 and r.json()["code"] == "TOO_SOON"
    assert _providers(client)[PAID]["paid_activation_step"] == 1
    assert client.post(f"{url}/disable", headers=h).json()["paid_activation_step"] == 0


def test_usage_budgets_and_summary(env: Env, owner_client: tuple[TestClient, dict[str, str]]) -> None:
    client, h = owner_client
    engine = create_engine(env.db_url)
    with engine.begin() as conn:
        key = conn.execute(
            text("SELECT to_char(now() AT TIME ZONE 'America/Los_Angeles', 'YYYY-MM-DD')")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO usage_records (provider_code, period_key, metric, amount, kind) "
                "VALUES ('gemini:gemini-3.8-flash', :k, 'REQUESTS', 50, 'RESERVE')"
            ),
            {"k": key},
        )
    engine.dispose()
    lines = client.get("/api/v1/usage", params={"period": "day"}).json()
    gem = next(
        x for x in lines if x["provider_code"] == "gemini:gemini-3.8-flash" and x["metric"] == "REQUESTS"
    )
    assert (gem["used"], gem["limit"], gem["pct"]) == (50, 200, 25)

    r = client.put("/api/v1/budgets", json={"scope": "STOCK", "cap_minor": 1000}, headers=h)
    assert r.status_code == 403  # raising a cap needs re-auth
    reauth(client, h)
    assert (
        client.put("/api/v1/budgets", json={"scope": "STOCK", "cap_minor": 1000}, headers=h).json()[
            "cap_minor"
        ]
        == 1000
    )
    assert (
        client.put("/api/v1/budgets", json={"scope": "PAID_PROVIDER", "cap_minor": 5}, headers=h).status_code
        == 400
    )
    assert [b["scope"] for b in client.get("/api/v1/budgets").json()] == ["STOCK"]
    assert client.get("/api/v1/costs/summary").json()["spent_minor"] == 0


def test_provider_codes_with_slashes_never_swallow_sub_resources(
    owner_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, h = owner_client
    # A raw "/" in the code still routes to the provider…
    assert client.patch(f"/api/v1/providers/{GROQ}", json={}, headers=idem(h)).status_code == 200
    # …but a sub-resource name is never read as part of a code: wrong method → 405, not 403/404.
    for sub in ("verify", "credentials", "paid-activation/step1"):
        r = client.patch(f"/api/v1/providers/{GROQ}/{sub}", json={}, headers=idem(h))
        assert r.status_code == 405, (sub, r.status_code)
