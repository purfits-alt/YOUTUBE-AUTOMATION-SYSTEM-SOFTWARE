"""ORM models match the generated schema; repository scoping, optimistic locking, soft delete."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from tubeforge.cli import alembic_config
from tubeforge.db.models import Base, Channel
from tubeforge.db.repository import (
    ChannelScope,
    NotFoundError,
    VersionConflictError,
    get_scoped,
    scoped_select,
    soft_delete,
    update_versioned,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def db(db_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    monkeypatch.setenv("TUBEFORGE_DATABASE_URL", db_url)
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_every_mapped_column_exists_with_matching_nullability(db: Session) -> None:
    inspector = inspect(db.get_bind())
    for table in Base.metadata.sorted_tables:
        db_cols = {c["name"]: c for c in inspector.get_columns(table.name)}
        for col in table.columns:
            assert col.name in db_cols, f"{table.name}.{col.name} missing in DB"
            if not col.primary_key:
                assert db_cols[col.name]["nullable"] == col.nullable, f"{table.name}.{col.name} nullability"


def _channel(db: Session, name: str) -> Channel:
    ch = Channel(name=name, state="ACTIVE", content_language="en")
    db.add(ch)
    db.flush()
    return ch


def test_scope_hides_other_channels(db: Session) -> None:
    a, b = _channel(db, "A"), _channel(db, "B")
    only_a = ChannelScope.only(a.id)
    assert [c.name for c in db.scalars(scoped_select(Channel, only_a))] == ["A"]
    assert {c.name for c in db.scalars(scoped_select(Channel, ChannelScope.all()))} == {"A", "B"}
    with pytest.raises(NotFoundError):
        get_scoped(db, Channel, b.id, only_a)  # out of scope looks like missing
    with pytest.raises(NotFoundError):
        get_scoped(db, Channel, uuid.uuid4(), ChannelScope.all())


def test_optimistic_locking(db: Session) -> None:
    ch = _channel(db, "A")
    assert update_versioned(db, Channel, ch.id, 1, {"name": "A2"}) == 2
    with pytest.raises(VersionConflictError) as err:
        update_versioned(db, Channel, ch.id, 1, {"name": "stale"})
    assert err.value.current == 2


def test_soft_delete_hides_row(db: Session) -> None:
    ch = _channel(db, "A")
    soft_delete(db, Channel, ch.id, ChannelScope.all())
    db.flush()
    assert list(db.scalars(scoped_select(Channel, ChannelScope.all()))) == []
    assert len(list(db.scalars(scoped_select(Channel, ChannelScope.all(), include_deleted=True)))) == 1
