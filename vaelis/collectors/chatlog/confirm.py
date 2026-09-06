"""Turning a rule hit into a concrete agenda candidate.

Two implementations behind one protocol:

- :class:`HeuristicConfirmer` — deterministic, on-device, zero token cost.
  Handles the common shapes ("明天下午三点开会") and refuses anything it cannot
  pin to a real time.
- an LLM confirmer (L2, cheap model) can be dropped in later for the messy
  remainder. Only the matched snippet may be sent (ADR-0010); L1 never does
  this work (ADR-0011).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, Protocol

from vaelis.agenda.rules import RuleHit

from .client import ChatMessage
from .timeparse import ParsedWhen, parse_when

# A deadline with no stated clock means "by end of that day"; anything else
# defaults to the morning rather than midnight, which would read as "yesterday".
_DEFAULT_CLOCK = {
    "ddl": time(23, 59),
    "meeting": time(9, 0),
    "class": time(8, 0),
    "task": time(9, 0),
}


@dataclass
class Candidate:
    title: str
    start_at: str
    kind: str
    is_change: bool = False
    end_at: Optional[str] = None
    # Provenance for the agenda heuristic. ``tier`` is the talker's declared
    # grade ("info" default, "task" human-prioritised); ``weight`` is the
    # numeric source weight the confirm module assigns (task > info). Both ride
    # through into the event evidence so the board / report can prioritise.
    tier: str = "info"
    weight: int = 1


class Confirmer(Protocol):
    def confirm(self, message: ChatMessage, hit: RuleHit) -> Optional[Candidate]:
        ...


def _title_from(message: ChatMessage, hit: RuleHit) -> str:
    """Short human-readable label: the topical keywords plus a text fragment."""
    text = " ".join(message.content.split())
    if len(text) <= 40:
        return text

    keyword = hit.matched_keywords[0] if hit.matched_keywords else ""
    if keyword:
        index = text.find(keyword)
        if index != -1:
            start = max(0, index - 12)
            return text[start : start + 40].strip() + "…"
    return text[:40].strip() + "…"


class HeuristicConfirmer:
    """Deterministic confirmer — no network, no model, no token spend."""

    def __init__(self, *, now_factory=datetime.now, tier_of=None):
        self._now = now_factory
        # Resolves a talker's declared grade. Defaults to "info" when unset or
        # unknown — the collector never auto-grades, so a missing hook means
        # everything is treated as plain info-tier (unchanged behaviour).
        self._tier_of = tier_of or (lambda t: "info")

    def confirm(self, message: ChatMessage, hit: RuleHit) -> Optional[Candidate]:
        now = self._now()
        when = parse_when(message.content, now=now)

        tier = self._tier_of(message.talker)
        is_task = tier == "task"

        # A bare clock with no date is too ambiguous to schedule ("三点见"
        # could be today or tomorrow); info-tier messages let the model path
        # handle those. A task-tier talker is human-prioritised, so we relax
        # the refusal and pin it to today — this is the "source weight" that
        # lets task messages enter the confirm path ahead of info ones.
        if when.day is None:
            if is_task and when.clock is not None:
                when = ParsedWhen(day=now.date(), clock=when.clock)
            else:
                return None

        start = when.to_datetime(
            base=when.day,
            default_clock=_DEFAULT_CLOCK.get(hit.category, time(9, 0)),
        )

        return Candidate(
            title=_title_from(message, hit),
            start_at=start.replace(second=0, microsecond=0).isoformat(),
            kind=hit.category,
            is_change=hit.is_change,
            tier=tier,
            weight=2 if is_task else 1,
        )


class NullConfirmer:
    """Accepts nothing — used when a deployment wants collection disabled."""

    def confirm(self, message: ChatMessage, hit: RuleHit) -> Optional[Candidate]:
        return None
