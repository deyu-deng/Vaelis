"""Collect → filter → confirm → ingest.

Order matters and is the privacy contract:

1. whitelist   — non-listed talkers are never read
2. dedupe      — webhook and sweep both deliver; only one wins
3. local rules — on-device; decides what may leave the machine at all
4. confirm     — heuristic first, model only for the remainder (snippet only)
5. ingest      — lands as ``pending`` for the human to confirm (ADR-0009)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from vaelis.agenda import AgendaService, get_service
from vaelis.agenda.rules import match as rule_match
from vaelis.agenda.rules import snippet

from .client import ChatlogClient, ChatlogUnavailable, ChatMessage
from .config import CollectorConfig
from .confirm import Candidate, Confirmer, HeuristicConfirmer
from .state import SeenStore

logger = logging.getLogger(__name__)

# Two events count as "the same thing rescheduled" when they fall on the same
# day and share this much of their keyword set.
_MATCH_KEYWORDS = ("组会", "例会", "会议", "开会", "答辩", "面试", "课", "培训", "宣讲", "聚餐")


@dataclass
class IngestReport:
    scanned: int = 0
    skipped_duplicate: int = 0
    skipped_not_whitelisted: int = 0
    filtered_out: int = 0
    unresolved: int = 0
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)

    @property
    def pending_ids(self) -> list[str]:
        return [*self.created, *self.updated]

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "skipped_duplicate": self.skipped_duplicate,
            "skipped_not_whitelisted": self.skipped_not_whitelisted,
            "filtered_out": self.filtered_out,
            "unresolved": self.unresolved,
            "created": list(self.created),
            "updated": list(self.updated),
        }


def _topic_tokens(text: str) -> set[str]:
    return {word for word in _MATCH_KEYWORDS if word in text}


class ChatlogPipeline:
    def __init__(
        self,
        *,
        config: Optional[CollectorConfig] = None,
        client: Optional[ChatlogClient] = None,
        service: Optional[AgendaService] = None,
        seen: Optional[SeenStore] = None,
        confirmer: Optional[Confirmer] = None,
    ):
        self.config = config or CollectorConfig.load()
        self.client = client or ChatlogClient(self.config.base_url)
        self.service = service or get_service()
        self.seen = seen or SeenStore()
        self.confirmer = confirmer or HeuristicConfirmer()

    # --- single message -----------------------------------------------------

    def handle_message(self, message: ChatMessage, report: IngestReport) -> None:
        report.scanned += 1

        if not self.config.allows(message.talker):
            report.skipped_not_whitelisted += 1
            return

        if not self.seen.mark_seen(message.msg_id):
            report.skipped_duplicate += 1
            return

        hit = rule_match(message.content)
        if hit is None:
            report.filtered_out += 1
            return

        candidate = self.confirmer.confirm(message, hit)
        if candidate is None:
            report.unresolved += 1
            return

        evidence = {
            "msg_id": message.msg_id,
            "talker": message.talker,
            "sent_at": message.sent_at,
            # Only the matched snippet is ever persisted or forwarded.
            "snippet": snippet(message.content),
        }

        target_id = self._find_change_target(candidate) if candidate.is_change else None

        result = self.service.ingest_candidate(
            title=candidate.title,
            start_at=candidate.start_at,
            end_at=candidate.end_at,
            kind=candidate.kind,
            source="wechat",
            evidence=evidence,
            target_event_id=target_id,
        )

        if not result.changed_fields:
            # Nothing actually moved — do not nag the user about a no-op.
            return

        if result.created:
            report.created.append(result.event.id)
        else:
            report.updated.append(result.event.id)

    def _find_change_target(self, candidate: Candidate) -> Optional[str]:
        """Best-effort: which existing event is this message rescheduling?

        Same day plus a shared topic word is a deliberately conservative test —
        a wrong guess would rewrite an unrelated entry, and the fallback
        (creating a separate pending entry) is cheap for the user to dismiss.
        """
        try:
            day = datetime.fromisoformat(candidate.start_at).date()
        except ValueError:
            return None

        wanted = _topic_tokens(candidate.title)
        if not wanted:
            return None

        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())

        for event in self.service.list_agenda(start, end):
            if event.source == "manual" or event.status in {"confirmed", "pending"}:
                if _topic_tokens(event.title) & wanted:
                    return event.id
        return None

    # --- batch --------------------------------------------------------------

    def run_once(self, day: Optional[date] = None) -> IngestReport:
        """Sweep every whitelisted talker for one day. Safe to call repeatedly."""
        report = IngestReport()

        if not self.config.enabled:
            logger.debug("chatlog collector disabled in config; nothing scanned")
            return report

        if not self.config.talkers:
            logger.warning("chatlog collector enabled but the whitelist is empty")
            return report

        for talker in self.config.talkers:
            try:
                messages = self.client.fetch(talker, day)
            except ChatlogUnavailable as exc:
                # Service down or WeChat logged out — surface once, keep going.
                logger.warning("chatlog fetch failed for %s: %s", talker, exc)
                continue

            for message in messages:
                self.handle_message(message, report)

        return report
