"""Controls, settings, idempotency and SSE (IMPLEMENTATION_ROADMAP Phase 3 tasks 7–8)."""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import OWNER_PASSWORD, Env, login

pytestmark = pytest.mark.integration


def _idem(h: dict[str, str], key: str | None = None) -> dict[str, str]:
    return {**h, "Idempotency-Key": key or str(uuid.uuid4())}


def test_emergency_stop_activate_replay_and_clear_with_step_up(
    owner_client: tuple[TestClient, dict[str, str]], env: Env
) -> None:
    c, h = owner_client
    assert c.get("/api/v1/system/controls").json()["emergency_stop"]["active"] is False

    missing = c.post("/api/v1/system/emergency-stop", json={"reason": "test"}, headers=h)
    assert missing.status_code == 400 and missing.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    key = str(uuid.uuid4())
    first = c.post("/api/v1/system/emergency-stop", json={"reason": "test"}, headers=_idem(h, key))
    assert first.status_code == 200 and first.json()["emergency_stop"]["active"] is True
    assert first.json()["emergency_stop"]["reason"] == "test"
    again = c.post("/api/v1/system/emergency-stop", json={"reason": "test"}, headers=_idem(h, key))
    assert again.json() == first.json() and again.headers["Idempotency-Replayed"] == "true"
    mismatch = c.post("/api/v1/system/emergency-stop", json={"reason": "other"}, headers=_idem(h, key))
    assert mismatch.status_code == 422 and mismatch.json()["code"] == "IDEMPOTENCY_MISMATCH"
    # One audit row for the action, none for the replay.
    assert env.sql("SELECT count(*) FROM audit_log WHERE action = 'system.emergency_stop'") == [(1,)]
    assert ("EMERGENCY_STOP",) in env.sql("SELECT kind FROM security_events")

    denied = c.post("/api/v1/system/emergency-stop/clear", json={"reason": "done"}, headers=_idem(h))
    assert denied.status_code == 403 and denied.json()["code"] == "REAUTH_REQUIRED"
    assert c.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=h).status_code == 204
    cleared = c.post("/api/v1/system/emergency-stop/clear", json={"reason": "done"}, headers=_idem(h))
    assert cleared.status_code == 200 and cleared.json()["emergency_stop"]["active"] is False


def test_who_may_press_and_clear(env: Env, add_user) -> None:  # type: ignore[no-untyped-def]
    add_user("viewer@example.com", "VIEWER")
    add_user("editor@example.com", "EDITOR")
    with env.client() as c:
        h = login(c, "viewer@example.com")
        assert c.post("/api/v1/system/emergency-stop", json={}, headers=_idem(h)).status_code == 403
    with env.client() as c:
        h = login(c, "editor@example.com")
        assert c.post("/api/v1/system/emergency-stop", json={}, headers=_idem(h)).status_code == 200
        c.post("/api/v1/auth/reauth", json={"password": OWNER_PASSWORD}, headers=h)
        assert c.post("/api/v1/system/emergency-stop/clear", json={}, headers=_idem(h)).status_code == 403


def test_kill_switches_and_publishing_switch(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    c, h = owner_client
    ks = c.post(
        "/api/v1/system/kill-switches",
        json={"scope": "AGENT", "target_id": "A11_SCRIPTWRITING", "reason": "testing"},
        headers=_idem(h),
    )
    assert ks.status_code == 200 and ks.json()["active"] is True
    controls = c.get("/api/v1/system/controls").json()
    assert [k["target_id"] for k in controls["kill_switches"]] == ["A11_SCRIPTWRITING"]
    assert c.delete(f"/api/v1/system/kill-switches/{ks.json()['id']}", headers=h).status_code == 204
    assert c.get("/api/v1/system/controls").json()["kill_switches"] == []
    assert c.delete(f"/api/v1/system/kill-switches/{ks.json()['id']}", headers=h).status_code == 404
    pub = c.post(
        "/api/v1/system/publishing-kill-switch", json={"active": True, "reason": "holiday"}, headers=_idem(h)
    )
    assert pub.json()["publishing_kill_switch"] is True
    bad = c.post(
        "/api/v1/system/kill-switches",
        json={"scope": "NOPE", "target_id": "x", "reason": "abc"},
        headers=_idem(h),
    )
    assert bad.status_code == 400


def test_settings_if_match(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    c, h = owner_client
    got = c.get("/api/v1/settings")
    assert got.headers["ETag"] == '"1"'
    body = {k: v for k, v in got.json().items() if k not in ("version", "updated_at")}
    body["disk_budget_gb"] = 150
    assert c.put("/api/v1/settings", json=body, headers=h).status_code == 428
    ok = c.put("/api/v1/settings", json=body, headers={**h, "If-Match": '"1"'})
    assert ok.status_code == 200 and ok.json()["disk_budget_gb"] == 150 and ok.headers["ETag"] == '"2"'
    stale = c.put("/api/v1/settings", json=body, headers={**h, "If-Match": '"1"'})
    assert (
        stale.status_code == 412
        and stale.json()["code"] == "VERSION_CONFLICT"
        and stale.json()["current_version"] == 2
    )
    bad_tz = c.put(
        "/api/v1/settings", json={**body, "owner_timezone": "Mars/Base"}, headers={**h, "If-Match": '"2"'}
    )
    assert bad_tz.status_code == 400


def test_sse_broadcasts_control_changes_and_replays(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    c, h = owner_client
    app = c.app
    app.state.sse_idle_limit_s = 1.0  # end the stream after 1 s without events (tests only)

    def press() -> None:
        c.post("/api/v1/system/emergency-stop", json={"reason": "sse"}, headers=_idem(h))

    timer = threading.Timer(0.3, press)
    timer.start()
    with c.stream("GET", "/api/v1/events/stream") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        text = "".join(stream.iter_text())
    timer.join()
    assert "event: control.changed" in text and '"active":true' in text and '"reason":"sse"' in text

    event_id = next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("id: "))
    previous = str(int(event_id) - 1)
    with c.stream("GET", "/api/v1/events/stream", headers={"Last-Event-ID": previous}) as stream:
        replayed = "".join(stream.iter_text())
    assert f"id: {event_id}" in replayed

    anonymous = TestClient(app, base_url="http://127.0.0.1:8765")
    assert anonymous.get("/api/v1/events/stream").status_code == 401


def test_log_filters_reject_nul_and_junk(owner_client: tuple[TestClient, dict[str, str]]) -> None:
    """Regression: ?kind=%00 reached PostgreSQL and became a 500 (contract test finding)."""
    client, _ = owner_client
    for url in (
        "/api/v1/security-events?kind=%00",
        "/api/v1/security-events?severity=LOUD",
        "/api/v1/audit-log?action=a%00b",
        "/api/v1/audit-log?entity_type=" + "x" * 65,
    ):
        assert client.get(url).status_code == 400, url
    assert client.get("/api/v1/security-events?kind=LOGIN_FAILED&severity=WARNING").status_code == 200
    assert client.get("/api/v1/audit-log?action=auth.login").status_code == 200
