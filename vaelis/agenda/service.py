"""Agenda business rules — the only surface other modules should use.

Owns the semantics the spec cares about: message-derived changes land as
``pending`` with a new/old diff, the user confirms or dismisses them, and
dismissal restores whatever was true before (ADR-0009). Manual entries are
facts and land ``confirmed`` immediately.

No HTTP, no LLM, no Mind knowledge. The collector hands over already-confirmed
candidates; the Mind writer pulls :meth:`AgendaService.daily_summary`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from . import store
from .store import AgendaValidationError, Event

# Fields a pending change may overwrite, and which we snapshot into prev_value.
_DIFFABLE = ("title", "start_at", "end_at")


class AgendaError(Exception):
    """Business-rule failure (not found, illegal transition, expired seq)."""


class EventNotFound(AgendaError):
    pass


class ConfirmSeqExpired(AgendaError):
    pass


@dataclass
class IngestResult:
    event: Event
    created: bool
    changed_fields: list[str]


class AgendaService:
    def __init__(self, db_path: Optional[Path | str] = None):
        self._db_path = db_path

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = store.connect(self._db_path)
        try:
            yield conn
        finally:
            conn.close()

    # --- reads --------------------------------------------------------------

    def list_agenda(
        self,
        start_from: Any = None,
        start_to: Any = None,
        *,
        include_cancelled: bool = False,
    ) -> list[Event]:
        """Default window is today 00:00 through tomorrow 23:59:59."""
        if start_from is None and start_to is None:
            today = datetime.now().date()
            start_from = datetime.combine(today, datetime.min.time())
            start_to = datetime.combine(today + timedelta(days=1), datetime.max.time())
        with self._conn() as conn:
            return store.list_events(
                conn,
                start_from=start_from,
                start_to=start_to,
                include_cancelled=include_cancelled,
            )

    def get(self, event_id: str) -> Event:
        with self._conn() as conn:
            event = store.get_event(conn, event_id)
        if event is None:
            raise EventNotFound(event_id)
        return event

    def list_pending(self) -> list[Event]:
        with self._conn() as conn:
            return store.list_events(conn, status="pending")

    # --- manual edits (user is the source of truth) -------------------------

    def create_manual(
        self,
        *,
        title: str,
        start_at: Any,
        end_at: Any = None,
        kind: str = "task",
    ) -> Event:
        with self._conn() as conn:
            return store.create_event(
                conn,
                title=title,
                start_at=start_at,
                end_at=end_at,
                kind=kind,
                status="confirmed",
                source="manual",
            )

    def update_manual(self, event_id: str, **fields: Any) -> Event:
        allowed = {"title", "start_at", "end_at", "kind"}
        unknown = set(fields) - allowed
        if unknown:
            raise AgendaValidationError(f"cannot edit field(s): {sorted(unknown)}")
        patch = {k: v for k, v in fields.items() if v is not None}
        with self._conn() as conn:
            if store.get_event(conn, event_id) is None:
                raise EventNotFound(event_id)
            updated = store.update_event(conn, event_id, **patch)
        assert updated is not None
        return updated

    def delete(self, event_id: str) -> None:
        with self._conn() as conn:
            if not store.delete_event(conn, event_id):
                raise EventNotFound(event_id)

    # --- message-derived changes (land as pending) --------------------------

    def ingest_candidate(
        self,
        *,
        title: str,
        start_at: Any,
        end_at: Any = None,
        kind: str = "task",
        source: str = "wechat",
        evidence: Optional[dict] = None,
        target_event_id: Optional[str] = None,
    ) -> IngestResult:
        """Record a model-confirmed candidate as a pending change.

        ``target_event_id`` marks this as a change to an existing event: the
        current values are snapshotted into ``prev_value`` so the board can
        show a before/after and ``dismiss`` can roll back.
        """
        if source == "manual":
            raise AgendaValidationError("manual entries must use create_manual()")

        with self._conn() as conn:
            seq = store.next_confirm_seq(conn)
            stamp = store.now_iso()

            if target_event_id:
                current = store.get_event(conn, target_event_id)
                if current is None:
                    raise EventNotFound(target_event_id)

                incoming = {
                    "title": (title or current.title).strip() or current.title,
                    "start_at": store.normalize_dt(start_at, field_name="start_at"),
                    "end_at": store.normalize_dt(end_at, field_name="end_at", required=False),
                }
                previous = {k: getattr(current, k) for k in _DIFFABLE}
                changed = [k for k in _DIFFABLE if incoming[k] != previous[k]]
                if not changed:
                    return IngestResult(event=current, created=False, changed_fields=[])

                updated = store.update_event(
                    conn,
                    target_event_id,
                    **incoming,
                    kind=kind or current.kind,
                    status="pending",
                    source=source,
                    evidence=evidence,
                    # Keep the oldest known-good snapshot if one is already
                    # pending, so repeated re-schedules stay rollback-able.
                    prev_value=current.prev_value or previous,
                    confirm_seq=seq,
                    confirm_seq_at=stamp,
                )
                assert updated is not None
                return IngestResult(event=updated, created=False, changed_fields=changed)

            created = store.create_event(
                conn,
                title=title,
                start_at=start_at,
                end_at=end_at,
                kind=kind,
                status="pending",
                source=source,
                evidence=evidence,
                confirm_seq=seq,
                confirm_seq_at=stamp,
            )
            return IngestResult(event=created, created=True, changed_fields=list(_DIFFABLE))

    # --- human decisions ----------------------------------------------------

    def confirm(self, event_id: str) -> Event:
        with self._conn() as conn:
            current = store.get_event(conn, event_id)
            if current is None:
                raise EventNotFound(event_id)
            if current.status != "pending":
                return current
            updated = store.update_event(
                conn,
                event_id,
                status="confirmed",
                prev_value=None,
                confirm_seq=None,
                confirm_seq_at=None,
            )
        assert updated is not None
        return updated

    def dismiss(self, event_id: str) -> Optional[Event]:
        """Reject a pending change.

        Rolls back to ``prev_value`` when the event existed before; deletes it
        when the message proposed a brand-new event. Returns ``None`` after a
        delete so callers can tell the two outcomes apart.
        """
        with self._conn() as conn:
            current = store.get_event(conn, event_id)
            if current is None:
                raise EventNotFound(event_id)
            if current.status != "pending":
                return current

            if not current.prev_value:
                store.delete_event(conn, event_id)
                return None

            restore = {k: current.prev_value.get(k) for k in _DIFFABLE}
            updated = store.update_event(
                conn,
                event_id,
                **restore,
                status="confirmed",
                prev_value=None,
                confirm_seq=None,
                confirm_seq_at=None,
            )
        return updated

    # --- DingTalk short-sequence protocol -----------------------------------

    def resolve_by_seq(self, seq: int, *, accept: bool) -> Optional[Event]:
        with self._conn() as conn:
            event = store.find_by_confirm_seq(conn, seq)
        if event is None:
            raise EventNotFound(f"confirm_seq={seq}")
        if not store.confirm_seq_is_live(event):
            raise ConfirmSeqExpired(f"confirm_seq={seq}")
        return self.confirm(event.id) if accept else self.dismiss(event.id)

    # --- Mind hand-off (consumed by the serial writer, not by this module) --

    def daily_summary(self, day: Optional[datetime] = None) -> str:
        """Human-readable markdown digest for one day."""
        target = (day or datetime.now()).date()
        start = datetime.combine(target, datetime.min.time())
        end = datetime.combine(target, datetime.max.time())
        events = self.list_agenda(start, end)

        lines = [f"# 日程摘要 {target.isoformat()}", ""]
        if not events:
            lines.append("- （当日无日程）")
            return "\n".join(lines) + "\n"

        for event in events:
            when = event.start_at[11:16] if len(event.start_at) >= 16 else event.start_at
            flag = "（待确认）" if event.status == "pending" else ""
            lines.append(f"- {when} [{event.kind}] {event.title}{flag} — 来源 {event.source}")
        return "\n".join(lines) + "\n"


_DEFAULT: Optional[AgendaService] = None


def get_service() -> AgendaService:
    """Process-wide default service (used by the HTTP layer)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AgendaService()
    return _DEFAULT
