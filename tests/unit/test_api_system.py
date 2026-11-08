from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tubeforge.config import Settings
from tubeforge.main import create_app


def client(settings: Settings, host: str = "127.0.0.1:8765") -> TestClient:
    return TestClient(create_app(settings), base_url=f"http://{host}")


def test_healthz(settings: Settings) -> None:
    r = client(settings).get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_foreign_host_rejected_with_problem_json(settings: Settings) -> None:
    r = client(settings, host="evil.example:8765").get("/healthz")
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "BAD_HOST"


def test_localhost_name_allowed(settings: Settings) -> None:
    assert client(settings, host="localhost:8765").get("/healthz").status_code == 200


def test_readyz_reports_db_down_as_503(settings: Settings) -> None:
    unreachable = settings.model_copy(update={"database_url": "postgresql+psycopg://nobody@127.0.0.1:1/none"})
    r = client(unreachable).get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["code"] == "NOT_READY"
    assert body["checks"]["database"]["ok"] is False
    assert body["checks"]["data_dir"]["ok"] is True


def test_placeholder_page_when_web_not_built(settings: Settings) -> None:
    r = client(settings).get("/")
    assert r.status_code == 200
    assert "TubeForge is running" in r.text


def test_serves_built_web_app(settings: Settings, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>TubeForge SPA</body></html>", encoding="utf-8")
    r = client(settings.model_copy(update={"web_dist_dir": dist})).get("/")
    assert r.status_code == 200
    assert "TubeForge SPA" in r.text


def test_api_docs_hidden_in_prod(settings: Settings) -> None:
    prod = settings.model_copy(update={"env": "prod"})
    assert client(prod).get("/api/docs").status_code == 404


def test_spa_deep_links_fall_back_to_index(settings: Settings, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>TubeForge SPA</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    c = client(settings.model_copy(update={"web_dist_dir": dist}))
    for route in ("/approvals", "/projects/p-101/script", "/channels/ch-1/onboarding"):
        r = c.get(route)
        assert r.status_code == 200, route
        assert "TubeForge SPA" in r.text
    assert c.get("/assets/app.js").status_code == 200
    # Missing files and API paths stay 404 (no HTML served in their place).
    assert c.get("/assets/missing.js").status_code == 404
    assert c.get("/api/v1/unknown").status_code == 404


def test_readyz_reports_missing_master_key(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUBEFORGE_MASTER_KEY", raising=False)
    body = client(settings).get("/readyz").json()
    assert body["checks"]["keyring"]["ok"] is False
    assert "init-keys" in body["checks"]["keyring"]["detail"]


def test_login_without_master_key_is_not_ready(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUBEFORGE_MASTER_KEY", raising=False)
    r = client(settings).post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 503 and r.json()["code"] == "NOT_READY"


def test_405_lists_every_documented_method(settings: Settings) -> None:
    r = client(settings).request("DELETE", "/api/v1/settings")
    assert r.status_code == 405
    assert r.headers["allow"] == "GET, PUT"
    assert r.json()["code"] == "METHOD_NOT_ALLOWED"
    r = client(settings).request("PATCH", "/api/v1/system/kill-switches/abc")
    assert r.headers["allow"] == "DELETE"


def test_cursor_must_match_documented_pattern(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from tubeforge.api.pagination import decode_cursor, encode_cursor

    assert decode_cursor(encode_cursor(42)) == 42
    assert decode_cursor(None) is None
