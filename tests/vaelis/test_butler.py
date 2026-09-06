"""B5 管家包：早报 / 消息待办 digest / 额度预警 的数据收集、模板与 L2 改写。"""

from __future__ import annotations

import time

import pytest

from vaelis.agenda.service import AgendaService
from vaelis.butler.polish import polish
from vaelis.butler.report import (
    build_morning,
    build_quota_alert,
    build_todo_digest,
    format_morning,
    format_quota_alert,
    format_todo_digest,
)
from vaelis.quota.pool import QuotaPool
from vaelis.quota.sources import AigwSource, CheapApiSource, HealthStatus, SourceStatus


@pytest.fixture()
def svc(tmp_path):
    return AgendaService(tmp_path / "agenda.db")


def _src(name, kind, health=HealthStatus.HEALTHY, detail="test"):
    """A source whose probe returns a fixed health (no network)."""
    if kind == "cheap_api":
        src = CheapApiSource(name, model="m", base_url="http://x/v1", api_key="k")
    else:
        src = AigwSource(name, model="m", base_url="http://x/v1", api_key="k")
    src._probe_fn = lambda s: SourceStatus(s.name, s.kind, health, None, detail, time.time())
    return src


def _pool(**healths) -> QuotaPool:
    sources = {name: _src(name, kind, health) for name, (kind, health) in healths.items()}
    return QuotaPool(sources, order=list(sources))


@pytest.fixture()
def pool():
    return _pool(
        **{
            "zhipu-air": ("cheap_api", HealthStatus.HEALTHY),
            "antigravity": ("aigw", HealthStatus.DEGRADED),
            "workbuddy": ("aigw", HealthStatus.UNAVAILABLE),
        }
    )


# ── morning report ───────────────────────────────────────────────────────────


def test_build_morning_collects_three_sections(svc, pool):
    data = build_morning(svc, pool)
    assert set(data) == {"date", "change", "pending", "quota", "plan"}
    assert data["change"]["total"] == 0  # empty ledger
    assert data["pending"] == []
    assert data["plan"] is None
    assert [s["name"] for s in data["quota"]] == ["zhipu-air", "antigravity", "workbuddy"]


def test_format_morning_renders_all_sections(svc, pool):
    text = format_morning(build_morning(svc, pool))
    assert "早报" in text
    assert "改动率" in text
    assert "待批项" in text
    assert "昨夜计划: 无" in text
    assert "额度" in text
    assert "zhipu-air=healthy" in text
    assert "antigravity=degraded" in text


def test_format_morning_no_quota_data():
    data = {
        "date": "2026-09-02",
        "change": {"days": 7, "total": 0, "rate": None, "meets_target": True, "target": 0.2},
        "pending": [],
        "quota": [],
    }
    assert "无探针数据" in format_morning(data)
    assert "昨夜计划: 无" in format_morning(data)


def test_format_morning_reports_change_rate_verdict(svc, pool):
    svc.ingest_candidate(title="组会", start_at="2026-09-03T16:00:00")
    svc.confirm(svc.list_pending()[0].id)
    text = format_morning(build_morning(svc, pool))
    assert "改动率" in text and "达标" in text


# ── todo digest ──────────────────────────────────────────────────────────────


def test_build_todo_digest_only_message_derived(svc):
    svc.create_manual(title="自习", start_at="2026-09-03T19:00:00")  # manual → confirmed
    svc.ingest_candidate(title="组会", start_at="2026-09-03T16:00:00", source="wechat")
    data = build_todo_digest(svc)
    assert [e.title for e in data["items"]] == ["组会"]
    assert data["count"] == 1


def test_format_todo_digest_empty():
    assert "暂无待确认" in format_todo_digest({"count": 0, "items": []})


def test_format_todo_digest_lists_items(svc):
    svc.ingest_candidate(title="高数课改期", start_at="2026-09-03T10:00:00", source="wechat")
    text = format_todo_digest(build_todo_digest(svc))
    assert "待你决定" in text
    assert "高数课改期" in text


# ── quota alert ──────────────────────────────────────────────────────────────


def test_quota_alert_flags_degraded_and_unavailable(pool):
    data = build_quota_alert(pool)
    names = {s["name"] for s in data["alerts"]}
    assert names == {"antigravity", "workbuddy"}  # healthy 不预警


def test_format_quota_alert_renders_failing_sources(pool):
    text = format_quota_alert(build_quota_alert(pool))
    assert "额度预警" in text
    assert "antigravity" in text
    assert "workbuddy" in text
    assert "zhipu-air" not in text


def test_format_quota_alert_empty_when_all_healthy():
    pool = _pool(
        **{
            "zhipu-air": ("cheap_api", HealthStatus.HEALTHY),
            "antigravity": ("aigw", HealthStatus.HEALTHY),
            "workbuddy": ("aigw", HealthStatus.HEALTHY),
        }
    )
    assert build_quota_alert(pool)["alerts"] == []
    assert format_quota_alert(build_quota_alert(pool)) == ""


# ── L2 polish ────────────────────────────────────────────────────────────────


def test_polish_routes_through_injected_send():
    pool = _pool(**{"zhipu-air": ("cheap_api", HealthStatus.HEALTHY)})
    seen = {}

    def send(prompt, source):
        seen["prompt"] = prompt
        seen["source"] = source.name
        return "改写后的摘要"

    result = polish("原始文本", pool, send=send)
    assert result == "改写后的摘要"
    assert seen["source"] == "zhipu-air"
    assert "原始文本" in seen["prompt"]
