"""Database engine helpers (PostgreSQL via psycopg 3, SQLAlchemy 2.0)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3, "application_name": "tubeforge"},
    )


def check_database(database_url: str) -> tuple[bool, str]:
    """Return (ok, detail) without raising — used by /readyz."""
    try:
        with get_engine(database_url).connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        return False, type(exc).__name__
    return True, "ok"


def table_exists(database_url: str, table: str) -> bool:
    try:
        with get_engine(database_url).connect() as conn:
            found: bool = conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}).scalar_one()
    except Exception:
        return False
    return bool(found)
