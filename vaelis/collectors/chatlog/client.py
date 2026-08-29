"""Read-only HTTP client for the local chatlog service (127.0.0.1:5030).

chatlog decrypts the WeChat database locally; we only ever read, and only for
whitelisted talkers. Response shapes vary between chatlog versions, so the
normalizer is deliberately tolerant and every field has a fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


class ChatlogUnavailable(RuntimeError):
    """chatlog is not reachable (service down, WeChat logged out, …)."""


@dataclass(frozen=True)
class ChatMessage:
    msg_id: str
    talker: str
    sender: str
    sent_at: str
    content: str

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()


def _stable_id(talker: str, sent_at: str, content: str) -> str:
    digest = hashlib.sha1(f"{talker}|{sent_at}|{content}".encode("utf-8")).hexdigest()
    return f"cl_{digest[:16]}"


def _first(payload: dict, *names: str) -> Any:
    for name in names:
        if name in payload and payload[name] not in (None, ""):
            return payload[name]
    return None


def normalize_message(raw: Any, *, fallback_talker: str = "") -> Optional[ChatMessage]:
    """Map one chatlog record onto :class:`ChatMessage`, or ``None`` if unusable."""
    if not isinstance(raw, dict):
        return None

    content = _first(raw, "content", "Content", "msg", "message", "text")
    if content is None:
        return None
    content = str(content).strip()
    if not content:
        return None

    talker = str(_first(raw, "talker", "Talker", "chatroom", "roomId") or fallback_talker or "")
    sender = str(_first(raw, "senderName", "sender", "Sender", "nickname", "from") or "")
    sent_at = str(_first(raw, "time", "Time", "createTime", "timestamp", "date") or "")

    raw_id = _first(raw, "id", "msgId", "MsgId", "seq", "Seq")
    msg_id = f"cl_{raw_id}" if raw_id is not None else _stable_id(talker, sent_at, content)

    return ChatMessage(
        msg_id=msg_id,
        talker=talker,
        sender=sender,
        sent_at=sent_at,
        content=content,
    )


def _extract_records(payload: Any) -> Iterable[Any]:
    """chatlog answers with a bare list or a wrapper object depending on version."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "messages", "items", "list", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


class ChatlogClient:
    def __init__(self, base_url: str, *, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # Seam for tests: everything network-facing funnels through here.
    def _get(self, path: str, params: dict[str, str]) -> Any:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ChatlogUnavailable(f"chatlog request failed: {exc}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ChatlogUnavailable(f"chatlog returned non-JSON: {body[:120]}") from exc

    def healthy(self) -> bool:
        # chatlog v0.5.2 exposes only /health; older/newer builds may differ.
        try:
            self._get("/health", {})
        except ChatlogUnavailable:
            return False
        return True

    def fetch(self, talker: str, day: Optional[date] = None) -> list[ChatMessage]:
        """Fetch one talker's messages for one day.

        ``time`` and ``talker`` are both mandatory in the chatlog API; omitting
        the end date means "that single day".
        """
        if not talker:
            raise ValueError("talker is required — the whitelist must resolve first")

        target = (day or datetime.now().date()).isoformat()
        payload = self._get(
            "/api/v1/chatlog",
            {"time": target, "talker": talker, "format": "json"},
        )

        messages: list[ChatMessage] = []
        for raw in _extract_records(payload):
            message = normalize_message(raw, fallback_talker=talker)
            if message is not None and not message.is_empty:
                messages.append(message)
        return messages
