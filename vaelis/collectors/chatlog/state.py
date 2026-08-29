"""Dedupe ledger for collected messages.

The webhook and the 10-minute sweep both deliver the same message, so every
ingest path checks here first. Kept in its own database: the collector's
bookkeeping is not agenda state.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Long enough to cover a weekend of downtime, short enough to stay small.
RETENTION_DAYS = 30


def state_db_path() -> Path:
    override = os.environ.get("VAELIS_CHATLOG_STATE_DB", "").strip()
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        root = get_hermes_home() / "vaelis"
    except Exception:
        root = Path.home() / ".hermes" / "vaelis"
    return root / "chatlog_state.db"


class SeenStore:
    def __init__(self, db_path: Optional[Path | str] = None):
        self.path = Path(db_path) if db_path else state_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS seen (
                    msg_id  TEXT PRIMARY KEY,
                    seen_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_seen_at ON seen(seen_at);
                """
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def already_seen(self, msg_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM seen WHERE msg_id = ?", (msg_id,)).fetchone()
        return row is not None

    def mark_seen(self, msg_id: str) -> bool:
        """Record the id. Returns False when it was already there (a duplicate)."""
        stamp = datetime.now().replace(microsecond=0).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO seen (msg_id, seen_at) VALUES (?, ?)", (msg_id, stamp)
            )
            conn.commit()
        return cur.rowcount > 0

    def prune(self, *, retention_days: int = RETENTION_DAYS) -> int:
        # Inclusive bound so `retention_days=0` means "clear everything" rather
        # than sparing rows written in the current second.
        cutoff = (datetime.now() - timedelta(days=retention_days)).replace(microsecond=0).isoformat()
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM seen WHERE seen_at <= ?", (cutoff,))
            conn.commit()
        return cur.rowcount
