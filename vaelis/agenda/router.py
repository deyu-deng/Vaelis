"""HTTP adapter for the agenda service.

Thin by design: validate, call the service, map business errors to status
codes. Mounted at ``/api/agenda`` by ``hermes_cli.web_server`` so the desktop
board does not depend on an opt-in plugin being enabled (ADR-0008).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .service import (
    AgendaService,
    ConfirmSeqExpired,
    EventNotFound,
    get_service,
)
from .store import AgendaValidationError

router = APIRouter()


class EventCreate(BaseModel):
    title: str = Field(min_length=1)
    start_at: str
    end_at: Optional[str] = None
    kind: str = "task"


class EventPatch(BaseModel):
    title: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    kind: Optional[str] = None


def _service() -> AgendaService:
    return get_service()


def _serialize(event: Any) -> dict:
    return event.to_dict()


async def _call(func, *args, **kwargs):
    """Run blocking SQLite work off the event loop, mapping domain errors."""
    try:
        return await run_in_threadpool(func, *args, **kwargs)
    except EventNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConfirmSeqExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except AgendaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_agenda(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
):
    events = await _call(_service().list_agenda, from_, to)
    return [_serialize(e) for e in events]


@router.get("/pending")
async def list_pending():
    events = await _call(_service().list_pending)
    return [_serialize(e) for e in events]


@router.post("")
async def create_event(body: EventCreate):
    event = await _call(
        _service().create_manual,
        title=body.title,
        start_at=body.start_at,
        end_at=body.end_at,
        kind=body.kind,
    )
    return _serialize(event)


@router.patch("/{event_id}")
async def patch_event(event_id: str, body: EventPatch):
    event = await _call(
        _service().update_manual,
        event_id,
        **body.model_dump(exclude_none=True),
    )
    return _serialize(event)


@router.delete("/{event_id}")
async def delete_event(event_id: str):
    await _call(_service().delete, event_id)
    return {"ok": True, "id": event_id}


@router.post("/{event_id}/confirm")
async def confirm_event(event_id: str):
    event = await _call(_service().confirm, event_id)
    return _serialize(event)


@router.post("/{event_id}/dismiss")
async def dismiss_event(event_id: str):
    event = await _call(_service().dismiss, event_id)
    if event is None:
        return {"ok": True, "id": event_id, "deleted": True}
    return _serialize(event)
