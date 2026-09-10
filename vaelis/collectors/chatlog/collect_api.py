"""Board-facing collection API: the first-run review and the pending queue.

Mounted at ``/api/collect`` (see ``hermes_cli/web_server.py``). Consumed by
``apps/desktop/src/app/agenda/talker/api.ts`` — the desktop board's "session
collection" entry (A7 slice).

Contract (matches the desktop store):

* ``GET /api/collect/talkers``
      -> {reviewComplete: bool, talkers: [{id, name, status}]}
      status is one of known/excluded/pending; an unreviewed talker is
      reported as ``pending`` (board: "new session awaiting your decision")
      without being written to the status table.
* ``POST /api/collect/talkers/{talker}/mode``  body {mode: "collect"|"exclude"}
      -> {id, status}
      One-click collect/exclude from the board.
* ``POST /api/collect/talkers/bulk``  body {talkers: [...], status}
      Batch decision for the first-run review ("排除这批").
* ``POST /api/collect/review-complete``
      -> {reviewComplete: true}
      Flips the first-run gate; until this is called blacklist mode sweeps
      nothing (ADR-0010 revision).
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from .pipeline import ChatlogPipeline
from . import webhook as _webhook_module

logger = logging.getLogger(__name__)

router = APIRouter()


def get_pipeline() -> ChatlogPipeline:
    """Delegate to the webhook module's canonical singleton.

    There must be exactly one ``ChatlogPipeline`` per process — both the
    webhook ingest path and the board API operate on the same pipeline /
    talker store / seen store.  The webhook module owns the instance;
    this module only reads/writes through it.
    """
    return _webhook_module.get_pipeline()


def set_pipeline(pipeline: Optional[ChatlogPipeline]) -> None:
    """Injection seam for tests — proxies to the canonical holder."""
    _webhook_module.set_pipeline(pipeline)


def _status_for(talker: str) -> str:
    status = get_pipeline().talkers.status_of(talker)
    return status if status is not None else "pending"


class ModeDecision(BaseModel):
    mode: Literal["collect", "exclude"]


class BulkDecision(BaseModel):
    talkers: list[str]
    status: Literal["known", "excluded"]


@router.get("/talkers")
async def list_talkers():
    pipeline = get_pipeline()
    store = pipeline.talkers
    # Enumerate what chatlog actually has so the review covers every active
    # session; unknown entries surface as pending for a one-click decision.
    # `list_talker_sessions` also carries the chatlog display name (topicName)
    # so the board shows the real group/contact name, not the raw @chatroom id.
    try:
        sessions = await run_in_threadpool(pipeline.client.list_talker_sessions)
    except Exception as exc:  # pragma: no cover - network seam
        logger.warning("collect: session enumeration failed: %s", exc)
        sessions = []

    talkers = [
        {"id": session.id, "name": session.name or session.id, "status": _status_for(session.id)}
        for session in sessions
    ]
    return {
        "reviewComplete": store.review_done(),
        "talkers": talkers,
    }


@router.post("/talkers/{talker}/mode")
async def decide_talker(talker: str, decision: ModeDecision):
    store = get_pipeline().talkers
    status = "known" if decision.mode == "collect" else "excluded"
    store.set_status(talker, status)
    return {"id": talker, "status": status}


@router.post("/talkers/bulk")
async def decide_talkers_bulk(decision: BulkDecision):
    store = get_pipeline().talkers
    for talker in decision.talkers:
        store.set_status(talker, decision.status)
    return {"updated": len(decision.talkers), "status": decision.status}


@router.post("/review-complete")
async def complete_review():
    get_pipeline().talkers.set_review_done(True)
    return {"reviewComplete": True}
