"""Nightly next-day planner: read events, mark overlaps, write an evidenced plan.

Zero LLM. No commute/homework invention. Every ``plan_items`` row must carry
evidence (store refuses empty). Empty windows write an honest empty plan.
Confirmed plans are not overwritten. See Docs/DESIGN-M2-PLANNING.md §1–2.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

from . import store
from .store import AgendaValidationError, DailyPlan, Event, RoutineTemplate

EMPTY_PLAN_SUMMARY = "明天没有日程。今夜计划为空，不是没跑。"
EMPTY_PLAN_PUSH = "明天没有日程，计划为空"
_MESSAGE_EVIDENCE_KEYS = ("msg_id", "talker", "sent_at", "snippet")

# C4: anchor instances carry this marker in plan_items.evidence — never in the
# events vocabulary (meeting/ddl/class/task stays frozen).
ROUTINE_EVIDENCE_KIND = "routine"

# C5 project pace blocks: deterministic rules only, zero LLM.
PROJECT_BLOCK_EVIDENCE_KIND = "project_block"
MAX_BLOCK_MINUTES = 120  # 每块 ≤2h
MIN_BLOCK_MINUTES = 30  # 不足 30 分钟的零头空窗不排（无意义碎片）
DDL_LOOKAHEAD_DAYS = 14  # DDL 临近优先的排序窗口


def _as_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value))
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    return moment.replace(microsecond=0)


def _as_dt_opt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    return _as_dt(value)


def intervals_overlap(a_start: Any, a_end: Any, b_start: Any, b_end: Any) -> bool:
    """True when two events collide. Half-open [start, end); missing end is a point."""
    a_s = _as_dt(a_start)
    b_s = _as_dt(b_start)
    a_e = _as_dt_opt(a_end)
    b_e = _as_dt_opt(b_end)

    if a_e is None and b_e is None:
        return a_s == b_s
    if a_e is None:
        return b_s <= a_s < b_e
    if b_e is None:
        return a_s <= b_s < a_e
    return a_s < b_e and b_s < a_e


def _as_for_date(value: Any) -> str:
    if value is None:
        return (datetime.now().date() + timedelta(days=1)).isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    day = str(value).strip()
    if not day:
        raise AgendaValidationError("for_date is required")
    return day[:10]


def _day_window(day: str) -> tuple[datetime, datetime]:
    parsed = date.fromisoformat(day)
    start = datetime.combine(parsed, datetime.min.time())
    end = datetime.combine(parsed, datetime.max.time()).replace(microsecond=0)
    return start, end


def _item_evidence(event: Event) -> dict:
    payload: dict[str, Any] = {"kind": "event", "event_id": event.id}
    extra = event.evidence if isinstance(event.evidence, dict) else {}
    for key in _MESSAGE_EVIDENCE_KEYS:
        if extra.get(key) is not None:
            payload[key] = extra[key]
    return payload


def _conflict_map(events: list[Event]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {event.id: [] for event in events}
    for index, left in enumerate(events):
        for right in events[index + 1 :]:
            if intervals_overlap(left.start_at, left.end_at, right.start_at, right.end_at):
                mapping[left.id].append(right.id)
                mapping[right.id].append(left.id)
    return mapping


# --- routine anchors (C4) -----------------------------------------------------


def _hhmm_on(day: str, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.combine(date.fromisoformat(day), dt_time(hour, minute))


def anchor_span(template: RoutineTemplate, day: str) -> tuple[datetime, datetime]:
    """Template instantiated on ``day``. ``end < start`` ⇒ ends next day."""
    start = _hhmm_on(day, template.start_time)
    end = _hhmm_on(day, template.end_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def enabled_anchors_for_day(conn: Any, day: str) -> list[tuple[RoutineTemplate, datetime, datetime]]:
    """Enabled templates whose weekday matches ``day``, instantiated in order.

    没有模板就没有锚点——这里只读 ``routine_templates``，绝不凭空生成。
    """
    weekday = date.fromisoformat(day).weekday()
    anchors: list[tuple[RoutineTemplate, datetime, datetime]] = []
    for template in store.list_routine_templates(conn, enabled_only=True):
        if template.weekdays and weekday not in template.weekdays:
            continue
        start, end = anchor_span(template, day)
        anchors.append((template, start, end))
    anchors.sort(key=lambda entry: (entry[1], entry[0].id))
    return anchors


def _split_anchor_conflicts(
    anchors: list[tuple[RoutineTemplate, datetime, datetime]],
    events: list[Event],
) -> tuple[list[tuple[RoutineTemplate, datetime, datetime]], list[dict]]:
    """C4 rule: an anchor overlapping any event yields (not written, counted)."""
    kept: list[tuple[RoutineTemplate, datetime, datetime]] = []
    yielded: list[dict] = []
    for template, start, end in anchors:
        hits = sorted(
            event.id
            for event in events
            if intervals_overlap(start, end, event.start_at, event.end_at)
        )
        if hits:
            yielded.append(
                {
                    "template_id": template.id,
                    "title": template.title,
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "conflicts_with": hits,
                }
            )
        else:
            kept.append((template, start, end))
    return kept, yielded


def _anchor_item(template: RoutineTemplate, start: datetime, end: datetime) -> dict:
    return {
        "event_id": f"routine:{template.id}",
        "title": template.title,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "kind": "task",  # plan_items.kind stays in the event vocabulary
        "conflict_with": [],
        "evidence": {
            "kind": ROUTINE_EVIDENCE_KIND,
            "template_id": template.id,
        },
    }


# --- project pace blocks (C5) --------------------------------------------------


def paced_projects() -> list[tuple[Any, float]]:
    """``(entry, weekly_hours)`` for enabled role=l2_project entries with pace.

    pace 存在注册表（projects.yaml）而非 agenda.db：pace 是项目（agent 条目）
    的属性，与 provider/model 覆盖同类，注册表是项目清单唯一真源；agenda.db
    保持日程域内聚，不引入第二份项目身份副本。
    """
    from vaelis.agents.registry import load_registry

    out: list[tuple[Any, float]] = []
    try:
        entries = load_registry().entries()
    except Exception:
        return out
    for entry in entries:
        if entry.role != "l2_project" or entry.weekly_hours is None:
            continue
        out.append((entry, entry.weekly_hours))
    out.sort(key=lambda pair: pair[0].name)
    return out


def _occupied_intervals(
    conn: Any,
    day: str,
    events: list[Event],
    kept_anchors: list[tuple[RoutineTemplate, datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Everything blocking the day: timed events + anchors (incl. spillover).

    无 ``end_at`` 的事件（DDL 点）不占窗；前一天跨午夜锚点溢出的清晨段算占用。
    """
    occupied: list[tuple[datetime, datetime]] = []
    for event in events:
        if not event.end_at:
            continue
        start = max(_as_dt(event.start_at), window_start)
        end = min(_as_dt(event.end_at), window_end)
        if end > start:
            occupied.append((start, end))
    for _, start, end in kept_anchors:
        start = max(start, window_start)
        end = min(end, window_end)
        if end > start:
            occupied.append((start, end))
    prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    for _, start, end in enabled_anchors_for_day(conn, prev_day):
        if end > window_start:  # 跨午夜溢出段
            occupied.append((window_start, min(end, window_end)))
    return occupied


def _free_windows(
    occupied: list[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> list[list[datetime]]:
    """Chronological free gaps ≥ MIN_BLOCK_MINUTES, as mutable [start, end]."""
    clipped = sorted((s, e) for s, e in occupied if e > s)
    free: list[list[datetime]] = []
    cursor = window_start
    for start, end in clipped:
        if start > cursor:
            free.append([cursor, min(start, window_end)])
        cursor = max(cursor, end)
        if cursor >= window_end:
            break
    if cursor < window_end:
        free.append([cursor, window_end])
    return [gap for gap in free if gap[1] - gap[0] >= timedelta(minutes=MIN_BLOCK_MINUTES)]


def _next_ddl(conn: Any, entry_name: str, window_from: datetime) -> Optional[datetime]:
    """该项目的下一个 DDL 事件（kind=ddl 且标题含项目名），确定性启发式。

    events 表没有 project 外键，标题包含项目名是 MVP 能落地的确定性关联；
    匹配不到 = 无 DDL（排序垫底，按名称稳定）。
    """
    events = store.list_events(conn, start_from=window_from.isoformat())
    needle = entry_name.lower()
    best: Optional[datetime] = None
    for event in events:
        if event.kind != "ddl":
            continue
        if needle not in event.title.lower():
            continue
        moment = _as_dt(event.start_at)
        if best is None or moment < best:
            best = moment
    return best


def _project_block_items(
    conn: Any,
    day: str,
    events: list[Event],
    kept_anchors: list[tuple[RoutineTemplate, datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> tuple[list[dict], list[dict]]:
    """Fill free windows with project blocks: DDL-nearest first, ≤2h each,
    total ≤ weekly_hours/7. Overflow lands in ``unscheduled``."""
    paced = paced_projects()
    if not paced:
        return [], []

    occupied = _occupied_intervals(conn, day, events, kept_anchors, window_start, window_end)
    free = _free_windows(occupied, window_start, window_end)

    ddl_limit = window_start + timedelta(days=DDL_LOOKAHEAD_DAYS)

    def _sort_key(pair):
        ddl = _next_ddl(conn, pair[0].name, window_from=window_start)
        if ddl is not None and ddl > ddl_limit:
            ddl = None  # lookahead 之外的 DDL 视同无 DDL
        return (ddl is None, ddl or window_start, pair[0].name)

    ranked = sorted(paced, key=_sort_key)

    blocks: list[dict] = []
    unscheduled: list[dict] = []
    for entry, weekly_hours in ranked:
        budget = weekly_hours / 7.0 * 3600.0  # 秒
        for gap in free:
            if budget <= 0:
                break
            available = (gap[1] - gap[0]).total_seconds()
            if available <= 0:
                continue
            take = min(budget, available, MAX_BLOCK_MINUTES * 60.0)
            if take < MIN_BLOCK_MINUTES * 60.0:
                continue  # 剩余预算不足一个最小块，留给下一个项目/放弃
            start = gap[0]
            end = start + timedelta(seconds=take)
            blocks.append(
                {
                    "event_id": f"project:{entry.name}",
                    "title": f"推进 · {entry.name}",
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "kind": "task",
                    "conflict_with": [],
                    "evidence": {
                        "kind": PROJECT_BLOCK_EVIDENCE_KIND,
                        "project_id": entry.name,
                        "pace": f"weekly_hours:{weekly_hours:g}",
                    },
                }
            )
            gap[0] = end  # 该空窗被消耗
            budget -= take
        if budget > 0:
            unscheduled.append(
                {
                    "project": entry.name,
                    "missing_hours": round(budget / 3600.0, 1),
                }
            )
    return blocks, unscheduled


def _pending_summary(event_count: int, conflict_count: int) -> str:
    if conflict_count:
        return f"明天有{event_count}项日程，其中{conflict_count}处时间重叠。"
    return f"明天有{event_count}项日程，时间无重叠。"


def _plan_summary(
    event_count: int,
    pair_count: int,
    kept_anchors: list,
    yielded: list[dict],
    blocks: Optional[list[dict]] = None,
    unscheduled: Optional[list[dict]] = None,
) -> str:
    """One paragraph for L1 / DingTalk (L1 cost discipline unchanged)."""
    blocks = blocks or []
    unscheduled = unscheduled or []
    if not event_count:
        # No events — anchors / blocks alone are still a real plan.
        parts: list[str] = []
        if kept_anchors:
            parts.append(f"按作息模板安排了{len(kept_anchors)}项锚点")
        if blocks:
            parts.append(f"排了{len(blocks)}项项目推进块")
        if parts:
            text = "明天没有日程，" + "，".join(parts) + "。"
        else:
            text = EMPTY_PLAN_SUMMARY
    else:
        text = _pending_summary(event_count, pair_count)
        if kept_anchors:
            text += f"含{len(kept_anchors)}项作息锚点。"
        if blocks:
            text += f"另排{len(blocks)}项项目推进块。"
    if yielded:
        titles = "、".join(str(entry.get("title") or "") for entry in yielded)
        text += f"{len(yielded)}项锚点（{titles}）因与日程冲突让位。"
    if unscheduled:
        misses = "；".join(
            f"{entry['project']}（缺{entry['missing_hours']:g}小时）"
            for entry in unscheduled
        )
        text += f"未能安排：{misses}。"
    return text


def format_evening_plan_text(plan: DailyPlan, *, summary: Optional[str] = None) -> str:
    """DingTalk body. Empty plans always include ``EMPTY_PLAN_PUSH``."""
    text = plan.summary if summary is None else summary
    lines = [f"[Vaelis] 明日计划 {plan.for_date}", text]
    if plan.status == "empty" and EMPTY_PLAN_PUSH not in text:
        lines.append(EMPTY_PLAN_PUSH)
    elif plan.status == "pending" and plan.confirm_seq is not None:
        lines.append(f"回复：确认{plan.confirm_seq} / 忽略{plan.confirm_seq}")
    return "\n".join(lines)


def generate_evening_plan(
    for_date: Any = None,
    *,
    db_path: Path | str | None = None,
) -> DailyPlan:
    """Snapshot tomorrow (or ``for_date``) from events + routine anchors.

    Three-bucket model (DESIGN-M2-ROUTINE-ANCHORS-proposal §2): event items
    first, then user-authored routine anchors (C4). An anchor overlapping any
    event yields — it is not written and is counted in ``conflict_count``.
    ``event_count == 0`` with no surviving anchors → ``status=empty``; anchors
    alone make a real (``pending``) plan — templates are user-authorised fact,
    not invention. A ``confirmed`` row is returned unchanged.
    """
    day = _as_for_date(for_date)
    window_from, window_to = _day_window(day)
    conn = store.connect(db_path)
    try:
        existing = store.get_daily_plan(conn, day)
        if existing is not None and existing.status == "confirmed":
            return existing

        events = store.list_events(conn, start_from=window_from, start_to=window_to)
        anchors = enabled_anchors_for_day(conn, day)
        kept_anchors, yielded = _split_anchor_conflicts(anchors, events)
        blocks, unscheduled = _project_block_items(
            conn, day, events, kept_anchors, window_from, window_to
        )

        if not events and not kept_anchors and not blocks:
            plan = store.upsert_daily_plan(
                conn,
                for_date=day,
                status="empty",
                summary=EMPTY_PLAN_SUMMARY,
                conflict_count=0,
                event_count=0,
                confirm_seq=None,
                confirm_seq_at=None,
                evidence={
                    "kind": "empty_window",
                    "from": window_from.isoformat(),
                    "to": window_to.isoformat(),
                    "event_count": 0,
                },
            )
            store.replace_plan_items(conn, plan.id, [])
            stored = store.get_daily_plan(conn, day)
            assert stored is not None
            return stored

        conflicts = _conflict_map(events)
        pair_count = sum(len(ids) for ids in conflicts.values()) // 2
        # C4: a yielded anchor is a real conflict the user should see in the
        # header — the anchor gave way, so it cannot speak for itself.
        conflict_count = pair_count + len(yielded)
        seq = store.next_confirm_seq(conn)
        seq_at = store.now_iso()
        summary = _plan_summary(
            len(events), pair_count, kept_anchors, yielded, blocks, unscheduled
        )
        evidence: Optional[dict] = None
        if kept_anchors or yielded or blocks or unscheduled:
            evidence = {
                "kind": "evening_plan",
                "anchor_count": len(kept_anchors),
                "block_count": len(blocks),
            }
            if yielded:
                evidence["yielded_anchors"] = yielded
            if unscheduled:
                evidence["unscheduled"] = unscheduled
        plan = store.upsert_daily_plan(
            conn,
            for_date=day,
            status="pending",
            summary=summary,
            conflict_count=conflict_count,
            event_count=len(events),
            confirm_seq=seq,
            confirm_seq_at=seq_at,
            evidence=evidence,
        )
        items = []
        for index, event in enumerate(events):
            evidence = _item_evidence(event)
            if not evidence:
                raise AgendaValidationError("plan_items evidence is required")
            items.append(
                {
                    "event_id": event.id,
                    "title": event.title,
                    "start_at": event.start_at,
                    "end_at": event.end_at,
                    "kind": event.kind,
                    "sort_order": index,
                    "conflict_with": conflicts[event.id],
                    "evidence": evidence,
                }
            )
        for template, start, end in kept_anchors:
            items.append(_anchor_item(template, start, end))
        items.extend(blocks)
        items.sort(key=lambda item: str(item["start_at"]))
        for index, item in enumerate(items):
            item["sort_order"] = index
        store.replace_plan_items(conn, plan.id, items)
        stored = store.get_daily_plan(conn, day)
        assert stored is not None
        return stored
    finally:
        conn.close()


def l1_plan_view(
    for_date: Any,
    current_event_ids: Iterable[str],
    *,
    db_path: Path | str | None = None,
) -> dict:
    """L1-safe plan header. Never returns ``plan_items``."""
    day = _as_for_date(for_date)
    current = {str(item) for item in current_event_ids}
    conn = store.connect(db_path)
    try:
        plan = store.get_daily_plan(conn, day)
        if plan is None:
            return {
                "status": "missing",
                "summary": "昨夜未生成计划",
                "for_date": day,
                "event_count": 0,
                "conflict_count": 0,
                "stale": False,
                "empty": False,
            }
        planned = {item.event_id for item in store.list_plan_items(conn, plan.id)}
        return {
            "status": plan.status,
            "summary": plan.summary,
            "for_date": plan.for_date,
            "event_count": plan.event_count,
            "conflict_count": plan.conflict_count,
            "stale": planned != current,
            "empty": plan.status == "empty",
        }
    finally:
        conn.close()
