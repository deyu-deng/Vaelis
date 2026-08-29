"""Publish the day's agenda into Mind.

The coordinator between two modules that must not know each other: agenda
renders the digest, Mind persists it. Output lands under ``Loom/`` because
``Vault/`` forbids AI-authored prose (docs/specs/MIND_ADAPTER_PLAN.md §3).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from vaelis.mind import AI_WRITE_ROOT, MindWriter, WriteResult, get_writer

from .service import AgendaService, get_service

logger = logging.getLogger(__name__)


def summary_relative_path(day: Optional[datetime] = None) -> str:
    target = (day or datetime.now()).date().isoformat()
    return f"{AI_WRITE_ROOT}/{target}/agenda.md"


def publish_daily_summary(
    *,
    service: Optional[AgendaService] = None,
    writer: Optional[MindWriter] = None,
    day: Optional[datetime] = None,
) -> WriteResult:
    """Write one day's digest. Safe to re-run — it overwrites that day's file."""
    agenda = service or get_service()
    sink = writer or get_writer()

    if not sink.available:
        logger.info("mind: vault not configured; skipping agenda digest")
        return WriteResult(ok=False, written=[], skipped=[summary_relative_path(day)], detail="mind unavailable")

    return sink.write_one(summary_relative_path(day), agenda.daily_summary(day))
