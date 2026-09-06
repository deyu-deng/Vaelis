"""SQLite persistence for agenda events.

This module is deliberately dumb: schema, CRUD, queries. No business rules,
no LLM calls, no HTTP. Business semantics (pending/confirm, prev_value diffs,
evidence assembly) live in :mod:`vaelis.agenda.service`.

Runtime state lives here rather than in Mind because the board needs range
queries, diffs and evidence lookups — see docs/adr/0007-agenda-state-sqlite.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

# --- vocabulary (mirrors docs/specs/agenda-board.md) ------------------------

KINDS = ("meeting", "ddl", "class", "task")
STATUSES = ("pending", "confirmed", "cancelled")
SOURCES = ("wechat", "manual", "dingtalk", "timetable")
PLAN_STATUSES = ("empty", "pending", "confirmed", "dismissed")

# Human decision ledger (A5 change-rate metric, ADR-0009 byproduct).
ACTIONS = ("confirm", "dismiss", "manual_edit", "manual_delete")

CONFIRM_SEQ_TTL_HOURS = 24

_INIT_LOCK = threading.Lock()
_INITIALIZED: set[str] = set()


@dataclass
class Event:
    id: str
    title: str
    start_at: str
    kind: str = "task"
    status: str = "confirmed"
    source: str = "manual"
    end_at: Optional[str] = None
    evidence: Optional[dict] = None
    prev_value: Optional[dict] = None
    confirm_seq: Optional[int] = None
    confirm_seq_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DailyPlan:
    """One night's plan for a calendar day (M2). Not an event."""

    id: str
    for_date: str
    status: str = "pending"
    generated_at: str = ""
    summary: str = ""
    conflict_count: int = 0
    event_count: int = 0
    confirm_seq: Optional[int] = None
    confirm_seq_at: Optional[str] = None
    evidence: Optional[dict] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanItem:
    """One row in a daily plan; must point at an event and carry evidence."""

    id: str
    plan_id: str
    event_id: str
    title: str
    start_at: str
    kind: str = "task"
    end_at: Optional[str] = None
    sort_order: int = 0
    conflict_with: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["conflict_with"] = list(self.conflict_with)
        return data


ROUTINE_KIND = "routine"  # routine_templates.kind is fixed; never an events word

# C4 seed templates: editable examples, shipped disabled — the user turns them
# on after reviewing times. INSERT OR IGNORE keeps user edits intact.
ROUTINE_SEEDS: tuple[dict, ...] = (
    {
        "id": "seed-sleep",
        "title": "睡眠",
        "start_time": "23:30",
        "end_time": "07:30",  # 跨午夜：end < start → 结束在次日
        "weekdays": [],
    },
    {"id": "seed-breakfast", "title": "早餐", "start_time": "07:40", "end_time": "08:20", "weekdays": []},
    {"id": "seed-lunch", "title": "午餐", "start_time": "12:00", "end_time": "12:40", "weekdays": []},
    {"id": "seed-dinner", "title": "晚餐", "start_time": "18:30", "end_time": "19:10", "weekdays": []},
)


@dataclass
class RoutineTemplate:
    """A user-authored daily-routine anchor (C4). Evidence source, not an event."""

    id: str
    title: str
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"; earlier than start_time ⇒ ends next day
    weekdays: tuple[int, ...] = ()  # 0=Mon..6=Sun; empty ⇒ every day
    enabled: bool = False
    kind: str = ROUTINE_KIND
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["weekdays"] = list(self.weekdays)
        return data


class AgendaValidationError(ValueError):
    """Raised for caller-supplied values the store refuses to persist."""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def normalize_dt(value: Any, *, field_name: str, required: bool = True) -> Optional[str]:
    """Accept ISO8601 (with or without offset) and return a canonical string."""
    if value is None or value == "":
        if required:
            raise AgendaValidationError(f"{field_name} is required")
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise AgendaValidationError(f"{field_name} is not ISO8601: {value!r}") from exc
    return parsed.replace(microsecond=0).isoformat()


def agenda_db_path() -> Path:
    """Resolve the agenda DB path.

    Honours ``VAELIS_AGENDA_DB`` first (tests, unusual deployments), then the
    agent home. Never hardcodes a drive letter.
    """
    override = os.environ.get("VAELIS_AGENDA_DB", "").strip()
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        root = get_hermes_home() / "vaelis"
    except Exception:
        root = Path.home() / ".hermes" / "vaelis"
    return root / "agenda.db"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with WAL + row factory, initializing schema once."""
    path = Path(db_path) if db_path else agenda_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    key = str(path.resolve())
    if key not in _INITIALIZED:
        with _INIT_LOCK:
            if key not in _INITIALIZED:
                init_db(conn)
                _INITIALIZED.add(key)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create schema. Idempotent — safe to call on every connect."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id             TEXT PRIMARY KEY,
            title          TEXT NOT NULL,
            start_at       TEXT NOT NULL,
            end_at         TEXT,
            kind           TEXT NOT NULL DEFAULT 'task',
            status         TEXT NOT NULL DEFAULT 'confirmed',
            source         TEXT NOT NULL DEFAULT 'manual',
            evidence       TEXT,
            prev_value     TEXT,
            confirm_seq    INTEGER,
            confirm_seq_at TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_start_at ON events(start_at);
        CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
        CREATE TABLE IF NOT EXISTS action_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT NOT NULL,
            event_id     TEXT NOT NULL,
            action       TEXT NOT NULL,
            event_source TEXT NOT NULL,
            detail       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_action_log_ts ON action_log(ts);
        CREATE TABLE IF NOT EXISTS daily_plans (
            id             TEXT PRIMARY KEY,
            for_date       TEXT NOT NULL UNIQUE,
            status         TEXT NOT NULL,
            generated_at   TEXT NOT NULL,
            summary        TEXT NOT NULL DEFAULT '',
            conflict_count INTEGER NOT NULL DEFAULT 0,
            event_count    INTEGER NOT NULL DEFAULT 0,
            confirm_seq    INTEGER,
            confirm_seq_at TEXT,
            evidence       TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS plan_items (
            id            TEXT PRIMARY KEY,
            plan_id       TEXT NOT NULL,
            event_id      TEXT NOT NULL,
            title         TEXT NOT NULL,
            start_at      TEXT NOT NULL,
            end_at        TEXT,
            kind          TEXT NOT NULL DEFAULT 'task',
            sort_order    INTEGER NOT NULL DEFAULT 0,
            conflict_with TEXT,
            evidence      TEXT NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES daily_plans(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_plan_items_plan_sort
            ON plan_items(plan_id, sort_order);
        CREATE TABLE IF NOT EXISTS routine_templates (
            id         TEXT PRIMARY KEY,
            title      TEXT NOT NULL,
            kind       TEXT NOT NULL DEFAULT 'routine',
            start_time TEXT NOT NULL,
            end_time   TEXT NOT NULL,
            weekdays   TEXT,
            enabled    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkin_cards (
            id             TEXT PRIMARY KEY,
            for_date       TEXT NOT NULL,
            kind           TEXT NOT NULL DEFAULT 'checkin',
            status         TEXT NOT NULL DEFAULT 'pending',
            questions      TEXT,
            payload        TEXT,
            confirm_seq    INTEGER,
            confirm_seq_at TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            UNIQUE(for_date, kind)
        );
        """
    )
    _seed_routine_templates(conn)
    conn.commit()


logger = logging.getLogger(__name__)


# --- row mapping ------------------------------------------------------------


def _loads(raw: Any) -> Optional[dict]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        # Corrupted JSON in prev_value is dangerous: dismiss() treats
        # None prev_value as "delete the event entirely" rather than
        # rolling back. Surface the corruption so callers can handle it.
        logger.warning("agenda: corrupted JSON in database field: %r", raw[:200])
        return None
    return value if isinstance(value, dict) else None


def _dumps(value: Optional[dict]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _loads_list(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("agenda: corrupted JSON list in database field: %r", str(raw)[:200])
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _dumps_list(value: Iterable[str] | None) -> Optional[str]:
    if not value:
        return None
    return json.dumps(list(value), ensure_ascii=False)


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        title=row["title"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        kind=row["kind"],
        status=row["status"],
        source=row["source"],
        evidence=_loads(row["evidence"]),
        prev_value=_loads(row["prev_value"]),
        confirm_seq=row["confirm_seq"],
        confirm_seq_at=row["confirm_seq_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _validate_enum(value: str, allowed: Iterable[str], field_name: str) -> str:
    if value not in allowed:
        raise AgendaValidationError(
            f"{field_name} must be one of {sorted(allowed)}, got {value!r}"
        )
    return value


# --- CRUD -------------------------------------------------------------------


def create_event(
    conn: sqlite3.Connection,
    *,
    title: str,
    start_at: Any,
    end_at: Any = None,
    kind: str = "task",
    status: str = "confirmed",
    source: str = "manual",
    evidence: Optional[dict] = None,
    prev_value: Optional[dict] = None,
    confirm_seq: Optional[int] = None,
    confirm_seq_at: Optional[str] = None,
) -> Event:
    title = (title or "").strip()
    if not title:
        raise AgendaValidationError("title is required")
    _validate_enum(kind, KINDS, "kind")
    _validate_enum(status, STATUSES, "status")
    _validate_enum(source, SOURCES, "source")

    start = normalize_dt(start_at, field_name="start_at")
    end = normalize_dt(end_at, field_name="end_at", required=False)
    if end and start and end < start:
        raise AgendaValidationError("end_at must not precede start_at")

    stamp = now_iso()
    event = Event(
        id=f"evt_{uuid.uuid4().hex[:12]}",
        title=title,
        start_at=start or stamp,
        end_at=end,
        kind=kind,
        status=status,
        source=source,
        evidence=evidence,
        prev_value=prev_value,
        confirm_seq=confirm_seq,
        confirm_seq_at=confirm_seq_at,
        created_at=stamp,
        updated_at=stamp,
    )
    conn.execute(
        """
        INSERT INTO events (id, title, start_at, end_at, kind, status, source,
                            evidence, prev_value, confirm_seq, confirm_seq_at,
                            created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.title,
            event.start_at,
            event.end_at,
            event.kind,
            event.status,
            event.source,
            _dumps(event.evidence),
            _dumps(event.prev_value),
            event.confirm_seq,
            event.confirm_seq_at,
            event.created_at,
            event.updated_at,
        ),
    )
    conn.commit()
    return event


def get_event(conn: sqlite3.Connection, event_id: str) -> Optional[Event]:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _row_to_event(row) if row else None


def list_events(
    conn: sqlite3.Connection,
    *,
    start_from: Any = None,
    start_to: Any = None,
    status: Optional[str] = None,
    include_cancelled: bool = False,
) -> list[Event]:
    clauses: list[str] = []
    params: list[Any] = []

    lower = normalize_dt(start_from, field_name="from", required=False)
    upper = normalize_dt(start_to, field_name="to", required=False)
    if lower:
        clauses.append("start_at >= ?")
        params.append(lower)
    if upper:
        clauses.append("start_at <= ?")
        params.append(upper)
    if status:
        _validate_enum(status, STATUSES, "status")
        clauses.append("status = ?")
        params.append(status)
    elif not include_cancelled:
        clauses.append("status != 'cancelled'")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM events {where} ORDER BY start_at ASC, created_at ASC", params
    ).fetchall()
    return [_row_to_event(r) for r in rows]


_UPDATABLE = {
    "title",
    "start_at",
    "end_at",
    "kind",
    "status",
    "source",
    "evidence",
    "prev_value",
    "confirm_seq",
    "confirm_seq_at",
}


def update_event(conn: sqlite3.Connection, event_id: str, **fields: Any) -> Optional[Event]:
    unknown = set(fields) - _UPDATABLE
    if unknown:
        raise AgendaValidationError(f"unknown field(s): {sorted(unknown)}")
    if not fields:
        return get_event(conn, event_id)
    if get_event(conn, event_id) is None:
        return None

    assignments: list[str] = []
    params: list[Any] = []
    for name, value in fields.items():
        if name in {"kind", "status", "source"} and value is not None:
            allowed = {"kind": KINDS, "status": STATUSES, "source": SOURCES}[name]
            _validate_enum(value, allowed, name)
        if name in {"start_at", "end_at"} and value is not None:
            value = normalize_dt(value, field_name=name, required=(name == "start_at"))
        if name == "title":
            value = (value or "").strip()
            if not value:
                raise AgendaValidationError("title must not be empty")
        if name in {"evidence", "prev_value"}:
            value = _dumps(value)
        assignments.append(f"{name} = ?")
        params.append(value)

    assignments.append("updated_at = ?")
    params.append(now_iso())
    params.append(event_id)
    conn.execute(f"UPDATE events SET {', '.join(assignments)} WHERE id = ?", params)
    conn.commit()
    return get_event(conn, event_id)


def delete_event(conn: sqlite3.Connection, event_id: str) -> bool:
    cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    return cur.rowcount > 0


# --- decision ledger (A5) ---------------------------------------------------


def log_action(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    action: str,
    event_source: str,
    detail: Optional[str] = None,
) -> None:
    """Append one human decision. Append-only; never updated or deleted."""
    _validate_enum(action, ACTIONS, "action")
    conn.execute(
        """
        INSERT INTO action_log (ts, event_id, action, event_source, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_iso(), event_id, action, event_source, detail),
    )
    conn.commit()


def list_actions(
    conn: sqlite3.Connection,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> list[dict]:
    """Decisions newest-first as plain dicts; bounds are ISO timestamps."""
    clauses = []
    params: list[Any] = []
    if since:
        clauses.append("ts >= ?")
        params.append(since)
    if until:
        clauses.append("ts <= ?")
        params.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT id, ts, event_id, action, event_source, detail FROM action_log "
        f"{where} ORDER BY ts DESC, id DESC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# --- confirm sequence -------------------------------------------------------


def next_confirm_seq(conn: sqlite3.Connection) -> int:
    """Small per-day integer used by the DingTalk confirm protocol.

    Sequences restart daily so the numbers users type stay short; combined
    with the TTL check in :func:`confirm_seq_is_live` a stale reply cannot
    resolve a newer event. Events, daily_plans and checkin_cards share one
    namespace (DESIGN-M2 §4.1; C6 adds the third table — replies like
    ``确认3`` must resolve the newest issuer, so MAX spans all three).
    """
    today = datetime.now().date().isoformat()
    row = conn.execute(
        """
        SELECT MAX(top) AS top FROM (
            SELECT MAX(confirm_seq) AS top FROM events
             WHERE confirm_seq_at >= ?
            UNION ALL
            SELECT MAX(confirm_seq) AS top FROM daily_plans
             WHERE confirm_seq_at >= ?
            UNION ALL
            SELECT MAX(confirm_seq) AS top FROM checkin_cards
             WHERE confirm_seq_at >= ?
        )
        """,
        (today, today, today),
    ).fetchone()
    top = row["top"] if row and row["top"] is not None else 0
    return int(top) + 1


def find_by_confirm_seq(conn: sqlite3.Connection, seq: int) -> Optional[Event]:
    row = conn.execute(
        """
        SELECT * FROM events
        WHERE confirm_seq = ? AND status = 'pending'
        ORDER BY confirm_seq_at DESC LIMIT 1
        """,
        (int(seq),),
    ).fetchone()
    return _row_to_event(row) if row else None


def confirm_seq_is_live(
    row: Event | DailyPlan, *, now: Optional[datetime] = None
) -> bool:
    if not row.confirm_seq_at:
        return False
    try:
        issued = datetime.fromisoformat(row.confirm_seq_at)
    except ValueError:
        return False
    reference = now or datetime.now()
    return reference - issued <= timedelta(hours=CONFIRM_SEQ_TTL_HOURS)


def find_plan_by_confirm_seq(conn: sqlite3.Connection, seq: int) -> Optional[DailyPlan]:
    row = conn.execute(
        """
        SELECT * FROM daily_plans
        WHERE confirm_seq = ? AND status = 'pending'
        ORDER BY confirm_seq_at DESC LIMIT 1
        """,
        (int(seq),),
    ).fetchone()
    return _row_to_plan(row) if row else None


def _row_to_plan(row: sqlite3.Row) -> DailyPlan:
    return DailyPlan(
        id=row["id"],
        for_date=row["for_date"],
        status=row["status"],
        generated_at=row["generated_at"],
        summary=row["summary"] or "",
        conflict_count=int(row["conflict_count"] or 0),
        event_count=int(row["event_count"] or 0),
        confirm_seq=row["confirm_seq"],
        confirm_seq_at=row["confirm_seq_at"],
        evidence=_loads(row["evidence"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_item(row: sqlite3.Row) -> PlanItem:
    evidence = _loads(row["evidence"]) or {}
    return PlanItem(
        id=row["id"],
        plan_id=row["plan_id"],
        event_id=row["event_id"],
        title=row["title"],
        start_at=row["start_at"],
        kind=row["kind"] or "task",
        end_at=row["end_at"],
        sort_order=int(row["sort_order"] or 0),
        conflict_with=tuple(_loads_list(row["conflict_with"])),
        evidence=evidence,
    )


def get_daily_plan(conn: sqlite3.Connection, for_date: str) -> Optional[DailyPlan]:
    row = conn.execute(
        "SELECT * FROM daily_plans WHERE for_date = ?",
        (for_date,),
    ).fetchone()
    return _row_to_plan(row) if row else None


def get_daily_plan_by_id(conn: sqlite3.Connection, plan_id: str) -> Optional[DailyPlan]:
    row = conn.execute(
        "SELECT * FROM daily_plans WHERE id = ?",
        (plan_id,),
    ).fetchone()
    return _row_to_plan(row) if row else None


def upsert_daily_plan(
    conn: sqlite3.Connection,
    *,
    for_date: str,
    status: str,
    summary: str,
    conflict_count: int = 0,
    event_count: int = 0,
    confirm_seq: Optional[int] = None,
    confirm_seq_at: Optional[str] = None,
    evidence: Optional[dict] = None,
    generated_at: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> DailyPlan:
    """Insert or replace the plan header for ``for_date``. Does not touch items."""
    _validate_enum(status, PLAN_STATUSES, "status")
    day = str(for_date).strip()
    if not day:
        raise AgendaValidationError("for_date is required")
    stamp = now_iso()
    generated = generated_at or stamp
    existing = get_daily_plan(conn, day)
    pid = (plan_id or (existing.id if existing else "") or f"plan_{day}").strip()
    created_at = existing.created_at if existing else stamp
    conn.execute(
        """
        INSERT INTO daily_plans (
            id, for_date, status, generated_at, summary, conflict_count,
            event_count, confirm_seq, confirm_seq_at, evidence,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(for_date) DO UPDATE SET
            id=excluded.id,
            status=excluded.status,
            generated_at=excluded.generated_at,
            summary=excluded.summary,
            conflict_count=excluded.conflict_count,
            event_count=excluded.event_count,
            confirm_seq=excluded.confirm_seq,
            confirm_seq_at=excluded.confirm_seq_at,
            evidence=excluded.evidence,
            updated_at=excluded.updated_at
        """,
        (
            pid,
            day,
            status,
            generated,
            summary,
            int(conflict_count),
            int(event_count),
            confirm_seq,
            confirm_seq_at,
            _dumps(evidence),
            created_at,
            stamp,
        ),
    )
    conn.commit()
    stored = get_daily_plan(conn, day)
    assert stored is not None
    return stored


def set_plan_status(
    conn: sqlite3.Connection,
    plan_id: str,
    status: str,
    *,
    clear_seq: bool = False,
) -> Optional[DailyPlan]:
    _validate_enum(status, PLAN_STATUSES, "status")
    if get_daily_plan_by_id(conn, plan_id) is None:
        return None
    if clear_seq:
        conn.execute(
            """
            UPDATE daily_plans
               SET status = ?, confirm_seq = NULL, confirm_seq_at = NULL,
                   updated_at = ?
             WHERE id = ?
            """,
            (status, now_iso(), plan_id),
        )
    else:
        conn.execute(
            "UPDATE daily_plans SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), plan_id),
        )
    conn.commit()
    return get_daily_plan_by_id(conn, plan_id)


def list_plan_items(conn: sqlite3.Connection, plan_id: str) -> list[PlanItem]:
    rows = conn.execute(
        """
        SELECT * FROM plan_items
         WHERE plan_id = ?
         ORDER BY sort_order ASC, start_at ASC
        """,
        (plan_id,),
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def replace_plan_items(
    conn: sqlite3.Connection,
    plan_id: str,
    items: Iterable[PlanItem | dict],
) -> list[PlanItem]:
    """Replace all items for a plan. Empty evidence is refused."""
    if get_daily_plan_by_id(conn, plan_id) is None:
        raise AgendaValidationError(f"unknown plan_id {plan_id!r}")
    conn.execute("DELETE FROM plan_items WHERE plan_id = ?", (plan_id,))
    written: list[PlanItem] = []
    for index, raw in enumerate(items):
        if isinstance(raw, PlanItem):
            item = raw
        else:
            evidence = raw.get("evidence") or {}
            if not isinstance(evidence, dict) or not evidence:
                raise AgendaValidationError("plan_items evidence is required")
            event_id = str(raw.get("event_id") or "").strip()
            if not event_id:
                raise AgendaValidationError("plan_items event_id is required")
            item = PlanItem(
                id=str(raw.get("id") or f"pit_{uuid.uuid4().hex[:12]}"),
                plan_id=plan_id,
                event_id=event_id,
                title=str(raw.get("title") or "").strip(),
                start_at=normalize_dt(raw.get("start_at"), field_name="start_at") or "",
                kind=str(raw.get("kind") or "task"),
                end_at=normalize_dt(raw.get("end_at"), field_name="end_at", required=False),
                sort_order=int(raw.get("sort_order") if raw.get("sort_order") is not None else index),
                conflict_with=tuple(str(x) for x in (raw.get("conflict_with") or ())),
                evidence=evidence,
            )
        if not item.title.strip():
            raise AgendaValidationError("plan_items title is required")
        if not item.evidence:
            raise AgendaValidationError("plan_items evidence is required")
        if not item.event_id.strip():
            raise AgendaValidationError("plan_items event_id is required")
        _validate_enum(item.kind, KINDS, "kind")
        conn.execute(
            """
            INSERT INTO plan_items (
                id, plan_id, event_id, title, start_at, end_at, kind,
                sort_order, conflict_with, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                plan_id,
                item.event_id,
                item.title,
                item.start_at,
                item.end_at,
                item.kind,
                int(item.sort_order),
                _dumps_list(item.conflict_with),
                json.dumps(item.evidence, ensure_ascii=False),
            ),
        )
        written.append(item)
    conn.commit()
    return list_plan_items(conn, plan_id)


# --- routine templates (C4) --------------------------------------------------

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_hhmm(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not _HHMM_RE.match(text):
        raise AgendaValidationError(
            f"{field_name} must be HH:MM (00:00-23:59), got {value!r}"
        )
    return text


def _validate_weekdays(value: Any) -> tuple[int, ...]:
    """weekdays: JSON array of ints 0=Mon..6=Sun; empty/None ⇒ every day."""
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AgendaValidationError(f"weekdays is not valid JSON: {value!r}") from exc
    if not isinstance(value, (list, tuple)):
        raise AgendaValidationError("weekdays must be a list of ints 0-6")
    days = tuple(int(v) for v in value)
    for day in days:
        if not 0 <= day <= 6:
            raise AgendaValidationError(f"weekday out of range 0-6: {day}")
    return tuple(sorted(set(days)))


def _seed_routine_templates(conn: sqlite3.Connection) -> None:
    """Insert the default template set once; never overwrite user edits."""
    stamp = now_iso()
    for seed in ROUTINE_SEEDS:
        conn.execute(
            """
            INSERT OR IGNORE INTO routine_templates (
                id, title, kind, start_time, end_time, weekdays,
                enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                seed["id"],
                seed["title"],
                ROUTINE_KIND,
                seed["start_time"],
                seed["end_time"],
                _dumps_list([str(d) for d in seed["weekdays"]]) or "[]",
                stamp,
                stamp,
            ),
        )


def _row_to_template(row: sqlite3.Row) -> RoutineTemplate:
    weekdays_raw = row["weekdays"]
    try:
        weekdays = tuple(int(d) for d in json.loads(weekdays_raw)) if weekdays_raw else ()
    except (TypeError, json.JSONDecodeError):
        weekdays = ()
    return RoutineTemplate(
        id=row["id"],
        title=row["title"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        weekdays=weekdays,
        enabled=bool(row["enabled"]),
        kind=row["kind"] or ROUTINE_KIND,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def upsert_routine_template(
    conn: sqlite3.Connection,
    *,
    template_id: str = "",
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    weekdays: Any = None,
    enabled: bool = False,
) -> RoutineTemplate:
    """Create or update one routine template. ``kind`` is fixed to ``routine``."""
    title = str(title or "").strip()
    if not title:
        raise AgendaValidationError("title is required")
    start = _validate_hhmm(start_time, "start_time")
    end = _validate_hhmm(end_time, "end_time")
    if start == end:
        raise AgendaValidationError("start_time and end_time must differ")
    days = _validate_weekdays(weekdays)
    stamp = now_iso()
    tid = str(template_id or "").strip() or f"rt_{uuid.uuid4().hex[:12]}"
    existing = get_routine_template(conn, tid)
    created_at = existing.created_at if existing else stamp
    conn.execute(
        """
        INSERT INTO routine_templates (
            id, title, kind, start_time, end_time, weekdays,
            enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            kind=excluded.kind,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            weekdays=excluded.weekdays,
            enabled=excluded.enabled,
            updated_at=excluded.updated_at
        """,
        (
            tid,
            title,
            ROUTINE_KIND,
            start,
            end,
            _dumps_list([str(d) for d in days]) or "[]",
            1 if enabled else 0,
            created_at,
            stamp,
        ),
    )
    conn.commit()
    stored = get_routine_template(conn, tid)
    assert stored is not None
    return stored


def get_routine_template(conn: sqlite3.Connection, template_id: str) -> Optional[RoutineTemplate]:
    row = conn.execute(
        "SELECT * FROM routine_templates WHERE id = ?", (str(template_id),)
    ).fetchone()
    return _row_to_template(row) if row else None


def list_routine_templates(
    conn: sqlite3.Connection, *, enabled_only: bool = False
) -> list[RoutineTemplate]:
    sql = "SELECT * FROM routine_templates"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY start_time ASC, id ASC"
    rows = conn.execute(sql).fetchall()
    return [_row_to_template(r) for r in rows]


def delete_routine_template(conn: sqlite3.Connection, template_id: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM routine_templates WHERE id = ?", (str(template_id),)
    )
    conn.commit()
    return cursor.rowcount > 0


# --- checkin cards (C6) -------------------------------------------------------

CARD_STATUSES = ("pending", "confirmed", "dismissed")
CHECKIN_KIND = "checkin"  # 回访卡；config_proposal 是 C6b 的配置提案卡


@dataclass
class CheckinCard:
    """One daily secretary check-in (or a C6b config proposal). ADR-0009 machine."""

    id: str
    for_date: str  # UNIQUE — 每天最多一条回访卡
    kind: str = CHECKIN_KIND
    status: str = "pending"
    questions: list = field(default_factory=list)  # [{key, text, evidence}]
    payload: dict = field(default_factory=dict)
    confirm_seq: Optional[int] = None
    confirm_seq_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _row_to_card(row: sqlite3.Row) -> CheckinCard:
    return CheckinCard(
        id=row["id"],
        for_date=row["for_date"],
        kind=row["kind"] or CHECKIN_KIND,
        status=row["status"] or "pending",
        questions=_loads_questions(row["questions"]),
        payload=_loads(row["payload"]) or {},
        confirm_seq=row["confirm_seq"],
        confirm_seq_at=row["confirm_seq_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _loads_questions(raw: Any) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def upsert_checkin_card(
    conn: sqlite3.Connection,
    *,
    for_date: str,
    kind: str = CHECKIN_KIND,
    questions: Optional[list] = None,
    payload: Optional[dict] = None,
    confirm_seq: Optional[int] = None,
    confirm_seq_at: Optional[str] = None,
    status: str = "pending",
) -> CheckinCard:
    """Insert or replace the card for ``for_date``. One card per day."""
    _validate_enum(status, CARD_STATUSES, "status")
    if kind not in (CHECKIN_KIND, "config_proposal"):
        raise AgendaValidationError(f"unknown card kind {kind!r}")
    day = str(for_date).strip()
    if not day:
        raise AgendaValidationError("for_date is required")
    stamp = now_iso()
    existing = get_checkin_card(conn, day, kind=kind)
    card_id = existing.id if existing else f"card_{day}_{kind}"
    conn.execute(
        """
        INSERT INTO checkin_cards (
            id, for_date, kind, status, questions, payload,
            confirm_seq, confirm_seq_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(for_date, kind) DO UPDATE SET
            status=excluded.status,
            questions=excluded.questions,
            payload=excluded.payload,
            confirm_seq=excluded.confirm_seq,
            confirm_seq_at=excluded.confirm_seq_at,
            updated_at=excluded.updated_at
        """,
        (
            card_id,
            day,
            kind,
            status,
            json.dumps(questions or [], ensure_ascii=False),
            _dumps(payload),
            confirm_seq,
            confirm_seq_at,
            existing.created_at if existing else stamp,
            stamp,
        ),
    )
    conn.commit()
    stored = get_checkin_card(conn, day, kind=kind)
    assert stored is not None
    return stored


def get_checkin_card(
    conn: sqlite3.Connection, for_date: str, *, kind: str = CHECKIN_KIND
) -> Optional[CheckinCard]:
    row = conn.execute(
        "SELECT * FROM checkin_cards WHERE for_date = ? AND kind = ?",
        (str(for_date), kind),
    ).fetchone()
    return _row_to_card(row) if row else None


def get_checkin_card_by_id(conn: sqlite3.Connection, card_id: str) -> Optional[CheckinCard]:
    row = conn.execute(
        "SELECT * FROM checkin_cards WHERE id = ?", (str(card_id),)
    ).fetchone()
    return _row_to_card(row) if row else None


def find_card_by_confirm_seq(
    conn: sqlite3.Connection, seq: int, *, kind: Optional[str] = None
) -> Optional[CheckinCard]:
    sql = "SELECT * FROM checkin_cards WHERE confirm_seq = ? AND status = 'pending'"
    params: list[Any] = [int(seq)]
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    row = conn.execute(sql + " ORDER BY confirm_seq_at DESC LIMIT 1", params).fetchone()
    return _row_to_card(row) if row else None


def set_card_status(
    conn: sqlite3.Connection,
    card_id: str,
    status: str,
    *,
    clear_seq: bool = False,
) -> Optional[CheckinCard]:
    _validate_enum(status, CARD_STATUSES, "status")
    if get_checkin_card_by_id(conn, card_id) is None:
        return None
    if clear_seq:
        conn.execute(
            """
            UPDATE checkin_cards
               SET status = ?, confirm_seq = NULL, confirm_seq_at = NULL,
                   updated_at = ?
             WHERE id = ?
            """,
            (status, now_iso(), card_id),
        )
    else:
        conn.execute(
            "UPDATE checkin_cards SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), card_id),
        )
    conn.commit()
    return get_checkin_card_by_id(conn, card_id)


def list_checkin_cards(
    conn: sqlite3.Connection,
    *,
    since: Optional[str] = None,
    kind: Optional[str] = None,
) -> list[CheckinCard]:
    """Cards newest-first. ``since`` bounds for_date (ISO day, inclusive)."""
    clauses, params = [], []
    if since:
        clauses.append("for_date >= ?")
        params.append(str(since))
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM checkin_cards {where} ORDER BY for_date DESC", params
    ).fetchall()
    return [_row_to_card(r) for r in rows]
