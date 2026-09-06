"""B5 管家包：早报 / 消息待办 digest / 额度预警 的数据收集与消息模板。

三个 cron job 共享这里的 ``build_*`` 收集与 ``format_*`` 模板。全部纯函数、
零 LLM，因此 cron 任务是 ``no_agent``（零 token 成本）——L1 秘书只转发、不进
生成循环（B5 禁区）。早报不含完整工具日志（R3 口径）：只带改动率结论、待批项
条数与额度健康，不逐条贴工具调用记录。

「L2 便宜模型生成」由 :mod:`vaelis.butler.polish` 提供可选改写（走 B3 额度池
便宜源，便宜优先 + aigw 兜底），默认关闭；模板是永远在线的确定基线。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from vaelis.agenda.dispatch import format_pending
from vaelis.agenda.service import AgendaService, get_service
from vaelis.agenda.stats import change_report
from vaelis.agenda.store import DailyPlan
from vaelis.quota.pool import QuotaPool, get_quota_pool

_PLAN_STATUS_LABEL = {
    "empty": "空",
    "pending": "待批",
    "confirmed": "已批",
    "dismissed": "已忽略",
}


# ── data collection ─────────────────────────────────────────────────────────


def build_morning(
    service: Optional[AgendaService] = None,
    pool: Optional[QuotaPool] = None,
    *,
    days: int = 7,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """收集早报三件套：改动率 + 待批项 + 额度健康。

    改动率沿用 A5 口径（连续 ``days`` 天统计，见 :func:`change_report`）；
    待批项 = ``status == pending`` 的日程改动（含消息来源与手动草稿）；
    额度 = 三源最新探针状态（默认探针无网络，诚实标注 degraded/unavailable）。
    """
    service = service or get_service()
    pool = pool or get_quota_pool()

    when = now or datetime.now()
    change = change_report(service, days=days, now=now)
    pending = service.list_pending()
    quota = [s.as_dict() for s in pool.probe_all()]
    # Last night's 20:00 run writes for_date = that next day = this morning's date.
    plan = service.get_plan(when.date().isoformat())

    return {
        "date": when.date().isoformat(),
        "change": change,
        "pending": pending,
        "quota": quota,
        "plan": plan,
    }


def build_todo_digest(service: Optional[AgendaService] = None) -> dict[str, Any]:
    """收集消息待办：仅消息来源（source != manual）的待确认改动。"""
    service = service or get_service()
    items = [e for e in service.list_pending() if e.source != "manual"]
    return {"count": len(items), "items": items}


def build_quota_alert(pool: Optional[QuotaPool] = None) -> dict[str, Any]:
    """收集额度预警：健康度在阈值以下（degraded/unavailable）的源。"""
    pool = pool or get_quota_pool()
    pool.probe_all()
    alerts = [s.as_dict() for s in pool.alert_statuses()]
    return {"alerts": alerts}


def _morning_plan_label(plan: DailyPlan | dict[str, Any] | None) -> str:
    """empty / pending / confirmed / dismissed / 无 — last night's next-day plan."""
    if plan is None:
        return "无"
    status = plan.status if isinstance(plan, DailyPlan) else plan.get("status")
    return _PLAN_STATUS_LABEL.get(str(status or ""), "无")


# ── message templates ────────────────────────────────────────────────────────


def format_morning(data: dict[str, Any]) -> str:
    """早报正文。R3 口径：结论 + 计数 + 健康，不贴工具日志。"""
    change = data["change"]
    pending = data["pending"]
    quota = data["quota"]

    lines = [f"[Vaelis] 早报 {data['date']}"]

    if change["total"] == 0:
        lines.append("改动率: 近 %d 天暂无落定动作" % change["days"])
    else:
        verdict = "达标" if change["meets_target"] else "超标"
        lines.append(
            "改动率: %.0f%%（%s，目标 ≤ %.0f%%）"
            % (change["rate"] * 100, verdict, change["target"] * 100)
        )

    lines.append("待批项: %d 条" % len(pending))
    lines.append("昨夜计划: %s" % _morning_plan_label(data.get("plan")))

    if not quota:
        lines.append("额度: 无探针数据")
    else:
        summary = " · ".join("%s=%s" % (s["name"], s["health"]) for s in quota)
        lines.append("额度: %s" % summary)

    return "\n".join(lines)


def format_todo_digest(data: dict[str, Any]) -> str:
    """消息待办 digest：逐条列出待确认的消息改动（复用 §7 卡片格式）。"""
    if data["count"] == 0:
        return "[Vaelis] 消息待办：暂无待确认的消息改动。"

    lines = ["[Vaelis] 消息待办（%d 条待你决定）" % data["count"]]
    for event in data["items"]:
        lines.append(format_pending(event))
    return "\n\n".join(lines)


def format_quota_alert(data: dict[str, Any]) -> str:
    """额度预警正文。无异常源时返回空串（调用方不推送）。"""
    if not data["alerts"]:
        return ""

    lines = ["[Vaelis] 额度预警：以下额度源状态异常"]
    for s in data["alerts"]:
        detail = (" — %s" % s["detail"]) if s.get("detail") else ""
        lines.append("- %s（%s）: %s%s" % (s["name"], s["kind"], s["health"], detail))
    return "\n".join(lines)
