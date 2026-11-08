from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tubeforge.config import Settings, get_settings
from tubeforge.queue import ensure_windows_event_loop_policy

# psycopg's async mode needs the selector event loop on Windows (same as the worker CLI).
ensure_windows_event_loop_policy()

TEST_DB_ENV = "TUBEFORGE_TEST_DATABASE_URL"


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Never read the developer's real config file during tests."""
    monkeypatch.setenv("TUBEFORGE_CONFIG", str(tmp_path / "absent.toml"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        home_dir=tmp_path,
        web_dist_dir=tmp_path / "no-web",
        database_url=os.environ.get(TEST_DB_ENV, "postgresql+psycopg://nobody@127.0.0.1:1/none"),
        log_json=True,
    )


@pytest.fixture
def db_url() -> str:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.fail(f"integration tests need {TEST_DB_ENV} (a throwaway PostgreSQL database)")
    return url
