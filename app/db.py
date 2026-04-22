from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings


def ensure_data_dir() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row[1] for row in rows}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    ensure_data_dir()
    with sqlite3.connect(settings.sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_points (
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL DEFAULT 0,
                points INTEGER NOT NULL DEFAULT 0,
                last_checkin_at TEXT DEFAULT NULL,
                PRIMARY KEY (user_id, group_id)
            )
            """
        )
        _ensure_column(conn, "user_points", "checkin_streak", "checkin_streak INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "user_points", "total_checkins", "total_checkins INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "user_points", "updated_at", "updated_at TEXT DEFAULT ''")
        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    ensure_data_dir()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
