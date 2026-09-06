"""Model-backed confirmer — the fallback for what the heuristic cannot pin.

The heuristic confirmer (``confirm.py``) refuses any message it cannot pin to a
real calendar day, because a bare clock ("三点见") is genuinely ambiguous. Those
land as ``unresolved`` today. This module spends a cheap L2 call on them.

Two contracts it must not break:

**Privacy (ADR-0010)** — only :func:`vaelis.agenda.rules.snippet` output ever
reaches the model. Never the raw message, never surrounding context, never a
history of the conversation.

**Cost (ADR-0011)** — this is L2 work. The route is resolved through
:mod:`vaelis.routing` and the secretary's model is rejected outright; wiring the
flagship here would put it back in the per-message loop ADR-0011 exists to end.

This is the first real consumer of ``vaelis/routing``. If it ever stops calling
:meth:`ModelConfirmer.route`, the routing table becomes decoration again.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, time
from typing import Callable, Optional, Protocol

from vaelis.agenda.rules import RuleHit, snippet
from vaelis.routing import L2_AGENDA, ModelRoute, ModelRouter, RoutingError, get_router

from .client import ChatMessage
from .confirm import Candidate, HeuristicConfirmer, _DEFAULT_CLOCK, _title_from
from .timeparse import parse_when

logger = logging.getLogger(__name__)

# Environment variable holding the *full* chat-completions URL. We deliberately
# do not guess a path: providers disagree on ``/v1`` prefixes and guessing wrong
# produces a confusing 404 deep inside the collector.
CHAT_URL_ENV = "VAELIS_L2_CHAT_URL"
API_KEY_ENV = "VAELIS_L2_API_KEY"

_DEFAULT_TIMEOUT = 20.0

_JSON_BLOCK = re.compile(r"\{[^{}]*\}", re.DOTALL)

_SYSTEM_PROMPT = (
    "你是日程抽取器。从给定的一条消息中抽出最多一个日程项。\n"
    "只输出一行 JSON，不要任何解释、不要 markdown 代码块：\n"
    '{"date":"YYYY-MM-DD","time":"HH:MM","title":"不超过20字"}\n'
    "规则：\n"
    "- date 必须是能确定的具体日期；无法确定就填 null\n"
    "- time 无法确定就填 null\n"
    "- 这条消息本身不是日程安排时，三个字段全部填 null\n"
)


class Completer(Protocol):
    """Sends a prompt to one model and returns its reply text."""

    def __call__(self, prompt: str, route: ModelRoute) -> Optional[str]:
        ...


def openai_compatible_completer(
    prompt: str,
    route: ModelRoute,
    *,
    chat_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> Optional[str]:
    """POST to any OpenAI-compatible ``/chat/completions`` endpoint.

    Raises when unconfigured, so callers can distinguish "no endpoint" from
    "model said nothing" — the first is an operator error worth surfacing.
    """
    url = (chat_url or os.environ.get(CHAT_URL_ENV, "")).strip()
    key = (api_key or os.environ.get(API_KEY_ENV, "")).strip()
    if not url:
        raise RoutingError(f"model confirmer has no endpoint; set {CHAT_URL_ENV}")
    if not key:
        raise RoutingError(f"model confirmer has no credential; set {API_KEY_ENV}")

    body = json.dumps(
        {
            "model": route.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    choices = payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    return content if isinstance(content, str) else None


def _build_prompt(text: str, hit: RuleHit, now: datetime) -> str:
    """Assemble the prompt. ``text`` must already be a snippet — ADR-0010."""
    weekday = "一二三四五六日"[now.weekday()]
    return (
        f"今天是 {now.date().isoformat()}（周{weekday}），现在 {now:%H:%M}。\n"
        f"消息已判定为类别「{hit.category}」"
        f"{'，且这是对既有安排的变更' if hit.is_change else ''}。\n"
        "消息片段：\n"
        f'"""\n{text}\n"""'
    )


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a reply that may carry prose."""
    match = _JSON_BLOCK.search(text or "")
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_candidate(
    reply: str,
    message: ChatMessage,
    hit: RuleHit,
    now: datetime,
) -> Optional[Candidate]:
    parsed = _extract_json(reply)
    if parsed is None:
        logger.debug("model confirmer returned no JSON; leaving unresolved")
        return None

    raw_day = parsed.get("date")
    if not isinstance(raw_day, str) or not raw_day.strip():
        return None
    try:
        day = date.fromisoformat(raw_day.strip())
    except ValueError:
        logger.debug("model confirmer returned an unparseable date: %r", raw_day)
        return None

    clock: Optional[time] = None
    raw_clock = parsed.get("time")
    if isinstance(raw_clock, str) and raw_clock.strip():
        try:
            clock = time.fromisoformat(raw_clock.strip())
        except ValueError:
            clock = None

    if clock is None:
        # Prefer whatever the deterministic parse found before falling back to
        # the category default — the local parser is free and usually right.
        clock = parse_when(message.content, now=now).clock or _DEFAULT_CLOCK.get(
            hit.category, time(9, 0)
        )

    title = parsed.get("title")
    if not isinstance(title, str) or not title.strip():
        title = _title_from(message, hit)

    return Candidate(
        title=" ".join(title.split())[:40],
        start_at=datetime.combine(day, clock).replace(second=0, microsecond=0).isoformat(),
        kind=hit.category,
        is_change=hit.is_change,
    )


class ModelConfirmer:
    """Resolve the messages the heuristic refused, using a cheap L2 model.

    Every failure path returns ``None`` so the pipeline keeps counting the
    message as ``unresolved`` instead of inventing a schedule entry.
    """

    def __init__(
        self,
        *,
        completer: Optional[Completer] = None,
        router: Optional[ModelRouter] = None,
        role: str = L2_AGENDA,
        now_factory: Callable[[], datetime] = datetime.now,
    ):
        self._completer = completer
        self._router = router
        self._role = role
        self._now = now_factory

    def route(self) -> ModelRoute:
        """The model route this confirmer will use.

        Raises :class:`RoutingError` when the role is L1 or points at a GUI-only
        surface — both would violate ADR-0011 and both are operator mistakes,
        so they fail loudly rather than silently degrading.
        """
        router = self._router or get_router()
        if router.is_l1(self._role):
            raise RoutingError(
                f"{self._role} is the secretary; ADR-0011 forbids routing "
                "per-message confirmation through L1"
            )
        route = router.resolve(self._role)
        if route.is_gui_surface:
            raise RoutingError(
                f"{self._role} points at a GUI-only surface ({route.qualified}); "
                "those belong to L3 workers"
            )
        return route

    def confirm(self, message: ChatMessage, hit: RuleHit) -> Optional[Candidate]:
        try:
            route = self.route()
        except RoutingError as exc:
            logger.warning("model confirmer disabled: %s", exc)
            return None

        if self._completer is None:
            logger.debug("model confirmer has no completer injected; leaving unresolved")
            return None

        now = self._now()
        # The only text allowed to leave the machine (ADR-0010).
        prompt = _build_prompt(snippet(message.content), hit, now)

        try:
            reply = self._completer(prompt, route)
        except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, RoutingError) as exc:
            logger.warning("model confirmer call failed (%s); leaving unresolved", exc)
            return None

        if not reply:
            return None
        return _to_candidate(reply, message, hit, now)


class FallbackConfirmer:
    """Deterministic first, model only for the remainder.

    This ordering *is* the cost and privacy discipline: a message the heuristic
    can pin down never leaves the machine, so model spend and exposure both stay
    proportional to the genuinely ambiguous remainder rather than to message
    volume.
    """

    def __init__(
        self,
        *,
        primary: Optional[object] = None,
        fallback: Optional[ModelConfirmer] = None,
        now_factory: Callable[[], datetime] = datetime.now,
    ):
        self._primary = primary or HeuristicConfirmer(now_factory=now_factory)
        self._fallback = fallback

    def confirm(self, message: ChatMessage, hit: RuleHit) -> Optional[Candidate]:
        candidate = self._primary.confirm(message, hit)
        if candidate is not None or self._fallback is None:
            return candidate
        return self._fallback.confirm(message, hit)
