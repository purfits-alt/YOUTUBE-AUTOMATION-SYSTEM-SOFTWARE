"""TubeForge settings.

Sources (highest priority first): init kwargs → environment variables (``TUBEFORGE_*``)
→ TOML file (``TUBEFORGE_CONFIG`` or ``<home>/config/tubeforge.toml``) → defaults.

Only non-secret configuration belongs in the TOML file. The server always binds to a
loopback address (OAUTH_SECURITY §2/§6); anything else is rejected at startup.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WINDOWS_DEFAULT_HOME = Path(r"D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE")
LOOPBACK_NAMES = {"localhost"}


def default_home() -> Path:
    """Owner install root on Windows (C3 decision); the repo checkout elsewhere."""
    env = os.environ.get("TUBEFORGE_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return WINDOWS_DEFAULT_HOME
    return REPO_ROOT


def _toml_path() -> Path:
    explicit = os.environ.get("TUBEFORGE_CONFIG")
    if explicit:
        return Path(explicit)
    return default_home() / "config" / "tubeforge.toml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TUBEFORGE_", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    home_dir: Path = Field(default_factory=default_home)
    data_dir: Path | None = None
    database_url: str = "postgresql+psycopg://tubeforge@127.0.0.1:5432/tubeforge"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    web_dist_dir: Path = REPO_ROOT / "apps" / "web" / "dist"
    # Contact shown in the User-Agent of research requests (Wikimedia asks API users for one, e.g. a
    # web page or e-mail address). Optional and owner-chosen; empty means no contact is sent.
    research_contact: str = Field(default="", max_length=200, pattern=r"^[^\r\n\x00]*$")

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value in LOOPBACK_NAMES:
            return value
        try:
            if ipaddress.ip_address(value).is_loopback:
                return value
        except ValueError:
            pass
        raise ValueError("TubeForge only listens on a loopback address (127.0.0.1, ::1 or localhost)")

    @field_validator("database_url")
    @classmethod
    def _postgres_psycopg(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("database_url must start with 'postgresql+psycopg://'")
        return value

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir if self.data_dir is not None else self.home_dir / "data"

    @property
    def libpq_dsn(self) -> str:
        """DSN for libpq/psycopg (Procrastinate) — the SQLAlchemy URL without the driver part."""
        return "postgresql://" + self.database_url.removeprefix("postgresql+psycopg://")

    @property
    def allowed_hosts(self) -> frozenset[str]:
        names = {self.host, "127.0.0.1", "localhost", "[::1]"}
        return frozenset({*names, *(f"{n}:{self.port}" for n in names)})

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=_toml_path()),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
