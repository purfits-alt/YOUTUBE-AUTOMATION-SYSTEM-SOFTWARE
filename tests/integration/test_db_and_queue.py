"""Integration tests against a throwaway PostgreSQL (TUBEFORGE_TEST_DATABASE_URL)."""

from __future__ import annotations

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tubeforge.cli import alembic_config
from tubeforge.config import Settings
from tubeforge.db.session import table_exists
from tubeforge.main import create_app
from tubeforge.queue import ProcrastinateQueue, build_app, task_name
from tubeforge_workers.cli import run as run_worker

pytestmark = pytest.mark.integration


@pytest.fixture
def migrated(db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("TUBEFORGE_DATABASE_URL", db_url)
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return db_url


def test_migrations_up_down_up(migrated: str) -> None:
    cfg = alembic_config()
    assert table_exists(migrated, "procrastinate_jobs")
    command.downgrade(cfg, "base")
    assert not table_exists(migrated, "procrastinate_jobs")
    engine = create_engine(migrated)
    with engine.connect() as conn:
        leftovers = conn.execute(
            text("SELECT count(*) FROM pg_proc WHERE proname LIKE 'procrastinate%'")
        ).scalar_one()
    engine.dispose()
    assert leftovers == 0
    command.upgrade(cfg, "head")
    assert table_exists(migrated, "procrastinate_jobs")


def test_readyz_ok_with_real_database(
    migrated: str, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64
    import os

    monkeypatch.setenv("TUBEFORGE_MASTER_KEY", base64.b64encode(os.urandom(32)).decode())
    app = create_app(settings.model_copy(update={"database_url": migrated}))
    r = TestClient(app, base_url="http://127.0.0.1:8765").get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready"


async def _job_status(dsn: str, job_id: int) -> str:
    app = build_app(dsn)
    async with app.open_async():
        job = await app.job_manager.get_job_status_async(job_id)
    return str(job.value)


@pytest.mark.parametrize(
    ("name", "queue", "profile"), [("mnt.ping", "maintenance", "light"), ("heavy.ping", "heavy", "heavy")]
)
async def test_queue_roundtrip(
    migrated: str, monkeypatch: pytest.MonkeyPatch, name: str, queue: str, profile: str
) -> None:
    dsn = "postgresql://" + migrated.removeprefix("postgresql+psycopg://")
    app = build_app(dsn)
    async with app.open_async():
        job_id = await ProcrastinateQueue(app).enqueue(
            name, queue=queue, idempotency_key=f"t-{name}", message="hi"
        )
    assert await _job_status(dsn, job_id) == "todo"

    monkeypatch.setenv("TUBEFORGE_DATABASE_URL", migrated)
    from tubeforge.config import get_settings

    get_settings.cache_clear()
    await run_worker(profile, once=True)
    assert await _job_status(dsn, job_id) == "succeeded"


async def test_idempotency_key_blocks_duplicate_waiting_job(migrated: str) -> None:
    from procrastinate.exceptions import AlreadyEnqueued

    dsn = "postgresql://" + migrated.removeprefix("postgresql+psycopg://")
    app = build_app(dsn)
    async with app.open_async():
        q = ProcrastinateQueue(app)
        await q.enqueue(task_name("mnt.ping"), queue="maintenance", idempotency_key="same", message="a")
        with pytest.raises(AlreadyEnqueued):
            await q.enqueue(task_name("mnt.ping"), queue="maintenance", idempotency_key="same", message="b")


def test_schema_v1_tables_constraints_and_seeds(migrated: str) -> None:
    engine = create_engine(migrated)
    with engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='public' AND tablename NOT LIKE 'procrastinate%'"
                )
            ).scalars()
        )
        roles = dict(
            conn.execute(
                text(
                    "SELECT r.name, count(rp.*) FROM roles r "
                    "LEFT JOIN role_permissions rp ON rp.role_id = r.id GROUP BY r.name"
                )
            ).all()
        )
        settings_rows = conn.execute(text("SELECT count(*) FROM system_settings")).scalar_one()
    engine.dispose()
    assert {"users", "sessions", "audit_log", "channels", "upload_jobs", "provider_registry"} <= tables
    assert len(tables - {"alembic_version"}) == 80
    assert roles["OWNER"] > roles["EDITOR"] > roles["REVIEWER"] > roles["VIEWER"] > 0
    assert settings_rows == 1


def test_append_only_and_enum_checks_are_enforced(migrated: str) -> None:
    from sqlalchemy.exc import DBAPIError, IntegrityError

    engine = create_engine(migrated)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO security_events (kind, severity) VALUES ('TEST', 'INFO')"))
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text("UPDATE security_events SET kind = 'X'"))
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text("DELETE FROM security_events"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO channels (id, name, state, content_language) "
                "VALUES (gen_random_uuid(), 'x', 'NOT_A_STATE', 'en')"
            )
        )
    engine.dispose()
