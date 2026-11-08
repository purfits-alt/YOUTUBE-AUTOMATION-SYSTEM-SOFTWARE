"""Shared fixtures for API integration tests: migrated DB, master key, owner, signed-in client."""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tubeforge.auth.passwords import hash_password
from tubeforge.cli import alembic_config
from tubeforge.config import Settings
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Role, User, UserRole
from tubeforge.db.session import get_engine
from tubeforge.main import create_app

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "correct horse battery staple 42"
VIEWER_EMAIL = "viewer@example.com"
BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture
def migrated_db(db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("TUBEFORGE_DATABASE_URL", db_url)
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    get_engine.cache_clear()
    return db_url


@pytest.fixture
def master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUBEFORGE_MASTER_KEY", base64.b64encode(os.urandom(32)).decode())


def _add_user(db_url: str, email: str, role: str, password: str = OWNER_PASSWORD) -> User:
    engine = create_engine(db_url)
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid7(), email=email, display_name=role.title(), password_hash=hash_password(password))
        db.add(user)
        db.flush()
        role_id = db.scalar(select(Role.id).where(Role.name == role))
        db.add(UserRole(user_id=user.id, role_id=role_id, channel_id=None))
        db.commit()
    engine.dispose()
    return user


@dataclass
class Env:
    app_settings: Settings
    db_url: str
    owner: User

    def client(self) -> TestClient:
        return TestClient(create_app(self.app_settings), base_url=BASE_URL)

    def sql(self, query: str, **params: object) -> list[tuple[object, ...]]:
        engine = create_engine(self.db_url)
        with engine.begin() as conn:
            rows = (
                [tuple(r) for r in conn.execute(text(query), params)]
                if query.lstrip().upper().startswith("SELECT")
                else (conn.execute(text(query), params) and [])
            )
        engine.dispose()
        return rows


@pytest.fixture
def env(migrated_db: str, master_key: None, settings: Settings) -> Iterator[Env]:
    owner = _add_user(migrated_db, OWNER_EMAIL, "OWNER")
    yield Env(
        app_settings=settings.model_copy(update={"database_url": migrated_db}),
        db_url=migrated_db,
        owner=owner,
    )
    get_engine.cache_clear()


def login(client: TestClient, email: str = OWNER_EMAIL, password: str = OWNER_PASSWORD) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": client.cookies["tf_csrf"]}


@pytest.fixture
def owner_client(env: Env) -> Iterator[tuple[TestClient, dict[str, str]]]:
    with env.client() as client:
        yield client, login(client)


@pytest.fixture
def add_user(env: Env):  # type: ignore[no-untyped-def]
    def _add(email: str, role: str) -> User:
        return _add_user(env.db_url, email, role)

    return _add
