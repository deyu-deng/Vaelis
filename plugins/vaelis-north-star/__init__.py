"""Vaelis North Star plugin — deep edge module (narrow public surface).

Public agent tool: ``vaelis`` (area + action).
Public HTTP: ``/api/plugins/vaelis-north-star/*`` (dashboard plugin_api).
Internals live under ``lib/`` and must not be imported by Electron/UI code.
"""

from __future__ import annotations

import logging
from typing import Any

from . import tools as T

logger = logging.getLogger(__name__)

TOOLSET = "vaelis_north_star"

_VAELIS_SCHEMA = {
    "name": "vaelis",
    "description": (
        "Vaelis North Star deep tool. Pass area=task|compute|preview|ops and an action. "
        "See docs/vaelis/north_star/API.md. Prefer summaries for Master; use HID/aigw "
        "via compute; reuse Hermes kanban/gateway/cron instead of reinventing them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "area": {
                "type": "string",
                "enum": ["task", "compute", "preview", "ops"],
                "description": "Subsystem façade",
            },
            "action": {
                "type": "string",
                "description": (
                    "task: enqueue|board|get|approve|reject|complete|update|"
                    "stage_status|stage_advance|stage_approve; "
                    "compute: route|hid_status|hid_run; "
                    "preview: push|list|latest; "
                    "ops: master_plan|master_summarize|morning_report|night_tick|"
                    "mobile_board|mobile_instruct|domain_list|domain_register|"
                    "diagnose|learn_observe|learn_drafts|learn_resolve"
                ),
            },
            "goal": {"type": "string"},
            "task_id": {"type": "string"},
            "risk": {"type": "string"},
            "domain": {"type": "string"},
            "summary": {"type": "string"},
            "result": {"type": "string"},
            "reason": {"type": "string"},
            "status": {"type": "string"},
            "stage": {"type": "string"},
            "surface": {"type": "string"},
            "route": {"type": "string"},
            "prefer": {"type": "string"},
            "prompt": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "object"}},
            "device_id": {"type": "string"},
            "mock": {"type": "boolean"},
            "include_raw": {"type": "boolean"},
            "title": {"type": "string"},
            "priority": {"type": "string"},
            "kind": {"type": "string"},
            "url": {"type": "string"},
            "path": {"type": "string"},
            "text": {"type": "string"},
            "auto_open": {"type": "boolean"},
            "limit": {"type": "integer"},
            "instruction": {"type": "string"},
            "id": {"type": "string"},
            "label": {"type": "string"},
            "default_risk": {"type": "string"},
            "enabled": {"type": "boolean"},
            "steps": {"type": "array", "items": {"type": "string"}},
            "draft_id": {"type": "string"},
            "approve": {"type": "boolean"},
            "error": {"type": "string"},
            "max_chars": {"type": "integer"},
            "mirror_kanban": {"type": "boolean"},
        },
        "required": ["area", "action"],
    },
}


def register(ctx) -> None:
    ctx.register_tool(
        name="vaelis",
        toolset=TOOLSET,
        schema=_VAELIS_SCHEMA,
        handler=T.vaelis,
        description=_VAELIS_SCHEMA["description"],
        emoji="🧭",
    )
    ctx.register_hook("pre_gateway_dispatch", _on_pre_gateway_dispatch)
    logger.info("vaelis-north-star: registered deep tool 'vaelis' + gateway hook")


def _on_pre_gateway_dispatch(event: Any = None, gateway: Any = None, **kwargs) -> Any:
    """Mobile commands → rewrite into prompts that call the deep ``vaelis`` tool."""
    raw = (getattr(event, "text", None) or "").strip()
    if not raw.lower().startswith("/vaelis"):
        return None

    parts = raw.split(maxsplit=2)
    cmd = parts[1].lower() if len(parts) > 1 else "board"
    arg = parts[2] if len(parts) > 2 else ""

    prompts = {
        "board": (
            "Call vaelis with area=ops action=mobile_board and reply with a concise "
            "status board (awaiting approvals first). No remote mouse."
        ),
        "status": "Call vaelis area=ops action=mobile_board and summarize for mobile.",
        "report": "Call vaelis area=ops action=morning_report and send the report.",
        "preview": (
            "Call vaelis area=preview action=list and summarize. "
            "User may also open the desktop preview panel manually anytime."
        ),
        "help": (
            "Explain /vaelis board|approve <id>|reject <id>|instruct <text>|report|preview. "
            "Use the vaelis tool (deep module). No remote mouse."
        ),
    }
    if cmd in prompts:
        return {"action": "rewrite", "text": prompts[cmd]}
    if cmd == "approve" and arg:
        return {
            "action": "rewrite",
            "text": (
                f"Human approved {arg.strip()} from mobile. "
                f"Call vaelis area=task action=approve task_id={arg.strip()} "
                f"(and stage_approve if needed). Confirm briefly."
            ),
        }
    if cmd == "reject" and arg:
        return {
            "action": "rewrite",
            "text": (
                f"Human rejected {arg.strip()} from mobile. "
                f"Call vaelis area=task action=reject task_id={arg.strip()}."
            ),
        }
    if cmd in {"instruct", "do"} and arg:
        return {
            "action": "rewrite",
            "text": (
                f"Mobile instruction: {arg}\n"
                "Call vaelis area=ops action=mobile_instruct with that instruction, "
                "then outline Master next steps. Do not take over the mouse."
            ),
        }
    return {"action": "rewrite", "text": prompts["help"]}
