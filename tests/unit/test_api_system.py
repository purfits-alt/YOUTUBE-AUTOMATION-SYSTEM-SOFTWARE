from __future__ import annotations

from pathlib import Path

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
