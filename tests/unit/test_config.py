from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tubeforge.config import WINDOWS_DEFAULT_HOME, Settings


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
def test_loopback_hosts_allowed(host: str) -> None:
    assert Settings(host=host).host == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])  # noqa: S104
def test_non_loopback_hosts_rejected(host: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(host=host)


def test_database_url_must_use_psycopg() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://x@localhost/db")


def test_libpq_dsn_strips_driver() -> None:
    s = Settings(database_url="postgresql+psycopg://u:p@127.0.0.1:5432/tf")
    assert s.libpq_dsn == "postgresql://u:p@127.0.0.1:5432/tf"


def test_env_overrides_and_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    toml = tmp_path / "tubeforge.toml"
    toml.write_text('port = 9001\nlog_level = "DEBUG"\n', encoding="utf-8")
    monkeypatch.setenv("TUBEFORGE_CONFIG", str(toml))
    monkeypatch.setenv("TUBEFORGE_LOG_LEVEL", "WARNING")
    s = Settings()
    assert s.port == 9001  # from TOML
    assert s.log_level == "WARNING"  # env beats TOML


def test_data_dir_defaults_under_home_with_spaces(tmp_path: Path) -> None:
    home = tmp_path / "YOUTUBE AUTOMATION SYSTEM SOFTWARE"
    s = Settings(home_dir=home)
    assert s.resolved_data_dir == home / "data"


def test_windows_default_home_is_owner_choice() -> None:
    assert str(WINDOWS_DEFAULT_HOME) in {r"D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE"}


def test_allowed_hosts_include_port() -> None:
    s = Settings(port=8765)
    assert {"127.0.0.1:8765", "localhost:8765", "127.0.0.1"} <= s.allowed_hosts
