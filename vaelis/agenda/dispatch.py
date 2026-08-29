"""Push pending changes to the phone and resolve the replies.

Implements the short-sequence protocol from
docs/adr/0009-agenda-change-pending-confirmation.md:

    [Vaelis] 3. 组会 改期
    2026-08-26 15:00 → 2026-08-26 16:00
    依据：明天的组会改到下午四点
    回复「确认 3」或「忽略 3」

Replies are matched here rather than by an agent: parsing two words does not
justify a model call, and L1 runs a flagship model (ADR-0011 cost discipline).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from vaelis.notify import Notifier, get_notifier

from .service import (
    AgendaService,
    ConfirmSeqExpired,
    EventNotFound,
    get_service,
)
from .store import Event

logger = logging.getLogger(__name__)

_ACCEPT_WORDS = ("确认", "确定", "同意", "confirm", "ok", "yes")
_REJECT_WORDS = ("忽略", "取消", "不用", "拒绝", "dismiss", "no")

_REPLY = re.compile(
    r"^\s*(?P<verb>[\u4e00-\u9fff]+|[a-zA-Z]+)\s*(?P<seq>\d{1,4})\s*$",
)


@dataclass
class ReplyCommand:
    seq: int
    accept: bool


def parse_reply(text: str) -> Optional[ReplyCommand]:
    """Match ``确认 3`` / ``忽略3`` / ``ok 3``. Anything else returns ``None``."""
    match = _REPLY.match(text or "")
    if not match:
        return None

    verb = match.group("verb").strip().lower()
    seq = int(match.group("seq"))

    if verb in _ACCEPT_WORDS:
        return ReplyCommand(seq=seq, accept=True)
    if verb in _REJECT_WORDS:
        return ReplyCommand(seq=seq, accept=False)
    return None


def _clock(value: Optional[str]) -> str:
    if not value:
        return "—"
    return value.replace("T", " ")[:16]


def format_pending(event: Event) -> str:
    """One notification body. Short: it is read on a phone lock screen."""
    seq = event.confirm_seq if event.confirm_seq is not None else "?"
    lines = [f"[Vaelis] {seq}. {event.title}"]

    previous = event.prev_value or {}
    old_start = previous.get("start_at")
    if old_start and old_start != event.start_at:
        lines.append(f"{_clock(old_start)} → {_clock(event.start_at)}")
    else:
        lines.append(_clock(event.start_at))

    snippet = (event.evidence or {}).get("snippet")
    if snippet:
        lines.append(f"依据：{snippet[:80]}")

    lines.append(f"回复「确认 {seq}」或「忽略 {seq}」")
    return "\n".join(lines)


class PendingDispatcher:
    def __init__(
        self,
        *,
        service: Optional[AgendaService] = None,
        notifier: Optional[Notifier] = None,
    ):
        self._service = service
        self._notifier = notifier

    @property
    def service(self) -> AgendaService:
        return self._service or get_service()

    @property
    def notifier(self) -> Notifier:
        return self._notifier or get_notifier()

    def notify_pending(self, events: Optional[list[Event]] = None) -> list[str]:
        """Push one message per pending event. Returns the ids actually sent."""
        targets = events if events is not None else self.service.list_pending()
        if not targets:
            return []

        if not self.notifier.configured:
            logger.info("agenda: %d pending change(s) but no notifier configured", len(targets))
            return []

        sent: list[str] = []
        for event in targets:
            outcome = self.notifier.send(format_pending(event))
            if outcome.ok:
                sent.append(event.id)
            else:
                # Leave it pending; the next sweep retries rather than losing it.
                logger.warning("agenda: notify failed for %s: %s", event.id, outcome.detail)
        return sent

    def handle_reply(self, text: str) -> Optional[str]:
        """Resolve a phone reply. Returns an ack, or ``None`` if not for us."""
        command = parse_reply(text)
        if command is None:
            return None

        try:
            resolved = self.service.resolve_by_seq(command.seq, accept=command.accept)
        except ConfirmSeqExpired:
            return f"[Vaelis] 序号 {command.seq} 已过期（超过 24 小时），请在看板上处理。"
        except EventNotFound:
            return f"[Vaelis] 没有待确认的 {command.seq} 号，可能已经处理过了。"

        if command.accept:
            title = resolved.title if resolved else str(command.seq)
            return f"[Vaelis] 已确认：{title}"

        if resolved is None:
            return f"[Vaelis] 已忽略 {command.seq} 号，该条目未加入日程。"
        return f"[Vaelis] 已忽略 {command.seq} 号，已恢复为 {_clock(resolved.start_at)}。"


_DEFAULT: Optional[PendingDispatcher] = None


def get_dispatcher() -> PendingDispatcher:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = PendingDispatcher()
    return _DEFAULT


def set_dispatcher(dispatcher: Optional[PendingDispatcher]) -> None:
    global _DEFAULT
    _DEFAULT = dispatcher
