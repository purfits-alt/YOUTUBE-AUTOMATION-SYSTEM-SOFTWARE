"""Repository helpers: mandatory channel scoping, optimistic locking, soft delete.

DATABASE_SCHEMA §0 / NFR-SEC-07: every query on a channel-scoped table must state which channels
the caller may see. ``ChannelScope.all()`` is explicit (owner / system) — there is no implicit
"no filter".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from tubeforge.db.models import Base, Channel


class NotFoundError(Exception):
    pass


class VersionConflictError(Exception):
    def __init__(self, current: int | None) -> None:
        super().__init__("version conflict")
        self.current = current


@dataclass(frozen=True)
class ChannelScope:
    """Which channels a query may touch. ``ids is None`` means every channel (explicitly)."""

    ids: frozenset[uuid.UUID] | None

    @classmethod
    def all(cls) -> ChannelScope:
        return cls(None)

    @classmethod
    def only(cls, *ids: uuid.UUID) -> ChannelScope:
        return cls(frozenset(ids))

    def allows(self, channel_id: uuid.UUID | None) -> bool:
        return self.ids is None or (channel_id is not None and channel_id in self.ids)


def _channel_column(model: type[Base]) -> Any:
    if model is Channel:
        return Channel.id
    column = getattr(model, "channel_id", None)
    if column is None:
        raise TypeError(f"{model.__name__} is not channel-scoped")
    return column


def scoped_select[M: Base](
    model: type[M], scope: ChannelScope, *, include_deleted: bool = False
) -> Select[M]:
    stmt = select(model)
    if scope.ids is not None:
        stmt = stmt.where(_channel_column(model).in_(scope.ids))
    if not include_deleted and hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
    return stmt


def get_scoped[M: Base](db: Session, model: type[M], obj_id: uuid.UUID, scope: ChannelScope) -> M:
    """Fetch one row the scope may see. Out-of-scope rows look exactly like missing ones (404)."""
    row = db.scalars(scoped_select(model, scope).where(model.id == obj_id)).first()  # type: ignore[attr-defined]
    if row is None:
        raise NotFoundError(f"{model.__name__} {obj_id}")
    return row


def update_versioned[M: Base](
    db: Session, model: type[M], obj_id: Any, expected_version: int, values: dict[str, Any]
) -> int:
    """UPDATE ... WHERE version = :v, bumping the version. Returns the new version or raises."""
    table_id = model.id  # type: ignore[attr-defined]
    result = db.execute(
        update(model)
        .where(table_id == obj_id, model.version == expected_version)  # type: ignore[attr-defined]
        .values(**values, version=expected_version + 1)
        .returning(model.version)  # type: ignore[attr-defined]
    )
    new_version = result.scalar_one_or_none()
    if new_version is None:
        current = db.scalar(select(model.version).where(table_id == obj_id))  # type: ignore[attr-defined]
        if current is None:
            raise NotFoundError(f"{model.__name__} {obj_id}")
        raise VersionConflictError(int(current))
    return int(new_version)


def soft_delete[M: Base](db: Session, model: type[M], obj_id: uuid.UUID, scope: ChannelScope) -> None:
    row = get_scoped(db, model, obj_id, scope)
    row.deleted_at = datetime.now(UTC)  # type: ignore[attr-defined]
