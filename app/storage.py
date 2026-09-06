from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS pinned_charts (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    chart_payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pinned_updated_at ON pinned_charts(updated_at DESC);
"""


def init_db() -> None:
    with sqlite3.connect(settings.db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_pin(pin_id: str, query: str, payload: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pinned_charts(id, query, chart_payload)
               VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET query=excluded.query,
                 chart_payload=excluded.chart_payload,
                 updated_at=CURRENT_TIMESTAMP""",
            (pin_id, query, json.dumps(payload, ensure_ascii=False)),
        )


def list_pins() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, query, chart_payload, created_at, updated_at "
            "FROM pinned_charts ORDER BY updated_at DESC"
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item['chart_payload'] = json.loads(item['chart_payload'])
        out.append(item)
    return out


def get_pin(pin_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, query, chart_payload, created_at, updated_at "
            "FROM pinned_charts WHERE id=?",
            (pin_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item['chart_payload'] = json.loads(item['chart_payload'])
    return item


def delete_pin(pin_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM pinned_charts WHERE id=?", (pin_id,))
    return cur.rowcount > 0
