"""Collector pipeline: whitelist, dedupe, snippet-only evidence, change matching."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from vaelis.agenda.service import AgendaService
from vaelis.collectors.chatlog.client import ChatMessage, normalize_message
from vaelis.collectors.chatlog.config import CollectorConfig
from vaelis.collectors.chatlog.confirm import HeuristicConfirmer
from vaelis.collectors.chatlog.pipeline import ChatlogPipeline, IngestReport
from vaelis.collectors.chatlog.state import SeenStore

NOW = datetime(2026, 8, 25, 10, 0)


class FakeClient:
    """Stands in for the chatlog HTTP service."""

    def __init__(self, by_talker: dict[str, list[ChatMessage]] | None = None, fail: bool = False):
        self.by_talker = by_talker or {}
        self.fail = fail
        self.calls: list[tuple[str, date | None]] = []

    def fetch(self, talker: str, day=None):
        self.calls.append((talker, day))
        if self.fail:
            from vaelis.collectors.chatlog.client import ChatlogUnavailable

            raise ChatlogUnavailable("boom")
        return self.by_talker.get(talker, [])

    def healthy(self):
        return not self.fail


def message(content: str, *, talker: str = "班级群", msg_id: str = "m1") -> ChatMessage:
    return ChatMessage(
        msg_id=msg_id,
        talker=talker,
        sender="导师",
        sent_at="2026-08-25 10:00:00",
        content=content,
    )


@pytest.fixture()
def pipeline(tmp_path):
    return ChatlogPipeline(
        config=CollectorConfig(talkers=["班级群"], enabled=True),
        client=FakeClient(),
        service=AgendaService(tmp_path / "agenda.db"),
        seen=SeenStore(tmp_path / "seen.db"),
        confirmer=HeuristicConfirmer(now_factory=lambda: NOW),
    )


def test_non_whitelisted_talker_is_never_read(pipeline):
    report = IngestReport()
    pipeline.handle_message(message("明天下午三点开会", talker="私人聊天"), report)

    assert report.skipped_not_whitelisted == 1
    assert pipeline.service.list_pending() == []
    # It must not even enter the dedupe ledger — we never looked at it.
    assert pipeline.seen.already_seen("m1") is False


def test_duplicate_message_is_ingested_once(pipeline):
    report = IngestReport()
    pipeline.handle_message(message("明天下午三点开组会"), report)
    pipeline.handle_message(message("明天下午三点开组会"), report)

    assert report.skipped_duplicate == 1
    assert len(pipeline.service.list_pending()) == 1


def test_chatter_is_filtered_before_any_confirm(pipeline):
    report = IngestReport()
    pipeline.handle_message(message("好的收到"), report)

    assert report.filtered_out == 1
    assert pipeline.service.list_pending() == []


def test_schedule_message_lands_pending_with_snippet_evidence(pipeline):
    report = IngestReport()
    pipeline.handle_message(message("明天下午三点开组会，别迟到"), report)

    pending = pipeline.service.list_pending()
    assert len(pending) == 1
    event = pending[0]
    assert event.status == "pending"
    assert event.source == "wechat"
    assert event.start_at == "2026-08-26T15:00:00"
    assert event.kind == "meeting"
    assert event.confirm_seq == 1
    assert event.evidence["talker"] == "班级群"
    assert "组会" in event.evidence["snippet"]
    assert report.created == [event.id]


def test_evidence_carries_only_a_snippet_not_the_whole_thread(pipeline):
    long_message = "明天下午三点开组会 " + ("闲聊内容 " * 200)
    report = IngestReport()
    pipeline.handle_message(message(long_message), report)

    evidence = pipeline.service.list_pending()[0].evidence
    assert len(evidence["snippet"]) <= 400
    assert len(evidence["snippet"]) < len(long_message)


def test_ambiguous_time_is_left_unresolved(pipeline):
    report = IngestReport()
    # A topical keyword and a clock, but no day — too ambiguous to schedule.
    pipeline.handle_message(message("三点开会吧"), report)

    assert report.unresolved == 1
    assert pipeline.service.list_pending() == []


def test_reschedule_updates_the_matching_event(pipeline):
    original = pipeline.service.create_manual(
        title="组会", start_at="2026-08-26T15:00:00", kind="meeting"
    )

    report = IngestReport()
    pipeline.handle_message(message("明天的组会改到下午四点", msg_id="m2"), report)

    assert report.updated == [original.id]
    updated = pipeline.service.get(original.id)
    assert updated.status == "pending"
    assert updated.start_at == "2026-08-26T16:00:00"
    assert updated.prev_value["start_at"] == "2026-08-26T15:00:00"


def test_unrelated_change_does_not_hijack_an_event(pipeline):
    pipeline.service.create_manual(title="组会", start_at="2026-08-26T15:00:00", kind="meeting")

    report = IngestReport()
    pipeline.handle_message(message("明天的聚餐改到六点", msg_id="m3"), report)

    # A separate pending entry, not a rewrite of the 组会 row.
    assert report.created and not report.updated


def test_run_once_respects_enabled_flag(tmp_path):
    disabled = ChatlogPipeline(
        config=CollectorConfig(talkers=["班级群"], enabled=False),
        client=FakeClient({"班级群": [message("明天下午三点开组会")]}),
        service=AgendaService(tmp_path / "agenda.db"),
        seen=SeenStore(tmp_path / "seen.db"),
        confirmer=HeuristicConfirmer(now_factory=lambda: NOW),
    )

    report = disabled.run_once()
    assert report.scanned == 0
    assert disabled.client.calls == []


def test_run_once_sweeps_each_whitelisted_talker(tmp_path):
    client = FakeClient(
        {
            "班级群": [message("明天下午三点开组会", msg_id="a1")],
            "项目群": [message("周三上午十点答辩", msg_id="b1", talker="项目群")]
        }
    )
    pipeline = ChatlogPipeline(
        config=CollectorConfig(talkers=["班级群", "项目群"], enabled=True),
        client=client,
        service=AgendaService(tmp_path / "agenda.db"),
        seen=SeenStore(tmp_path / "seen.db"),
        confirmer=HeuristicConfirmer(now_factory=lambda: NOW),
    )

    report = pipeline.run_once()
    assert [call[0] for call in client.calls] == ["班级群", "项目群"]
    assert len(report.created) == 2


def test_run_once_survives_chatlog_being_down(tmp_path):
    pipeline = ChatlogPipeline(
        config=CollectorConfig(talkers=["班级群"], enabled=True),
        client=FakeClient(fail=True),
        service=AgendaService(tmp_path / "agenda.db"),
        seen=SeenStore(tmp_path / "seen.db"),
        confirmer=HeuristicConfirmer(now_factory=lambda: NOW),
    )

    report = pipeline.run_once()
    assert report.scanned == 0


def test_empty_whitelist_collects_nothing(tmp_path):
    pipeline = ChatlogPipeline(
        config=CollectorConfig(talkers=[], enabled=True),
        client=FakeClient({"班级群": [message("明天下午三点开组会")]}),
        service=AgendaService(tmp_path / "agenda.db"),
        seen=SeenStore(tmp_path / "seen.db"),
        confirmer=HeuristicConfirmer(now_factory=lambda: NOW),
    )

    assert pipeline.run_once().scanned == 0


def test_config_whitelist_and_env_override(tmp_path, monkeypatch):
    path = tmp_path / "chatlog.json"
    CollectorConfig(talkers=["群A"], enabled=True).save(path)

    loaded = CollectorConfig.load(path)
    assert loaded.talkers == ["群A"]
    assert loaded.allows("群A") is True
    assert loaded.allows("群B") is False

    monkeypatch.setenv("VAELIS_CHATLOG_TALKERS", "群B, 群C")
    assert CollectorConfig.load(path).talkers == ["群B", "群C"]


def test_config_defaults_to_collecting_nothing(tmp_path):
    empty = CollectorConfig.load(tmp_path / "missing.json")
    assert empty.enabled is False
    assert empty.talkers == []
    assert empty.allows("任何人") is False


@pytest.mark.parametrize(
    "raw",
    [
        {"content": "明天开会", "talker": "群", "time": "2026-08-25 10:00:00", "id": 7},
        {"Content": "明天开会", "Talker": "群", "Time": "2026-08-25 10:00:00", "Seq": 7},
        {"msg": "明天开会", "chatroom": "群", "createTime": "2026-08-25 10:00:00"},
    ],
)
def test_normalizer_tolerates_response_shapes(raw):
    parsed = normalize_message(raw)
    assert parsed is not None
    assert parsed.content == "明天开会"
    assert parsed.msg_id


def test_normalizer_rejects_unusable_records():
    assert normalize_message({"content": "   "}) is None
    assert normalize_message({"nothing": 1}) is None
    assert normalize_message("not a dict") is None


def test_seen_store_prunes_old_rows(tmp_path):
    store = SeenStore(tmp_path / "seen.db")
    assert store.mark_seen("x") is True
    assert store.mark_seen("x") is False
    assert store.prune(retention_days=0) == 1
    assert store.already_seen("x") is False
