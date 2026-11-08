"""tubeforge-admin: create-owner (policy, once only), has-owner, reset-password."""

from __future__ import annotations

import pytest

from tests.integration.conftest import Env
from tubeforge import admin
from tubeforge.db.session import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def fresh(migrated_db: str, master_key: None, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("TUBEFORGE_DATABASE_URL", migrated_db)
    get_engine.cache_clear()
    from tubeforge.config import get_settings

    get_settings.cache_clear()
    return migrated_db


def test_create_owner_once_with_policy(
    fresh: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert admin.has_owner() == 1
    monkeypatch.setenv("TUBEFORGE_OWNER_PASSWORD", "short")
    with pytest.raises(SystemExit, match="rejected"):
        admin.create_owner("me@example.com", "Me")
    monkeypatch.setenv("TUBEFORGE_OWNER_PASSWORD", "maple quartz lantern 9 river")
    assert admin.create_owner("not-an-email", "Me") == 2
    assert admin.create_owner("me@example.com", "Me") == 0
    assert admin.has_owner() == 0
    assert admin.create_owner("second@example.com", "Two") == 0
    assert "already exists" in capsys.readouterr().out


def test_reset_password_unlocks_and_signs_out(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUBEFORGE_DATABASE_URL", env.db_url)
    from tubeforge.config import get_settings

    get_settings.cache_clear()
    env.sql("UPDATE users SET locked_until = now() + interval '1 hour', failed_login_count = 5")
    with env.client() as c:
        from tests.integration.conftest import login

        assert (
            c.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "x"}).status_code
            == 423
        )
        monkeypatch.setenv("TUBEFORGE_OWNER_PASSWORD", "maple quartz lantern 9 river")
        assert admin.reset_password("owner@example.com") == 0
        login(c, password="maple quartz lantern 9 river")
    assert admin.reset_password("nobody@example.com") == 2
    assert ("user.password_reset",) in env.sql("SELECT action FROM audit_log")
