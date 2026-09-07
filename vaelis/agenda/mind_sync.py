"""Publish the day's agenda into Mind.

The coordinator between two modules that must not know each other: agenda
renders the digest, Mind persists it.

Two targets (MIND_ADAPTER_PLAN.md 写接缝）：

- ``Loom/raw/chat-logs/digested/<date>/agenda.md`` — daily AI-authored log
  (the historical channel, kept for chat-log digests);
- ``Vault/projects/Vaelis/daily/<date>.md`` — the current-project daily
  snapshot inside the official brain's Vaelis subtree (user-approved write
  zone; the lowercase ``vaelis`` archive stays read-only).

Both funnel through the same serialized, model-free :class:`MindWriter`
service. Runtime state remains SQLite-only (ADR-0007) — these files are
day-scoped read-only snapshots for the second brain, never the source of
truth. Failures return ``ok=False`` and never block the conversation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from vaelis.mind import AI_WRITE_ROOT, MindWriter, WriteResult, get_writer
from vaelis.mind.paths import is_safe_relative

from .service import AgendaService, get_service

logger = logging.getLogger(__name__)

PROJECT_DAILY_PREFIX = "Vault/projects/Vaelis/daily"


def summary_relative_path(day: Optional[datetime] = None) -> str:
    target = (day or datetime.now()).date().isoformat()
    return f"{AI_WRITE_ROOT}/{target}/agenda.md"


def project_daily_relative_path(day: Optional[datetime] = None) -> str:
    """当日项目快照路径（kebab/date-safe：ISO 日期本身就是 kebab）。"""
    target = (day or datetime.now()).date().isoformat()
    return f"{PROJECT_DAILY_PREFIX}/{target}.md"


def publish_daily_summary(
    *,
    service: Optional[AgendaService] = None,
    writer: Optional[MindWriter] = None,
    day: Optional[datetime] = None,
) -> WriteResult:
    """Write one day's digest. Safe to re-run — it overwrites that day's file."""
    agenda = service or get_service()
    sink = writer or get_writer()

    if not sink.available:
        logger.info("mind: vault not configured; skipping agenda digest")
        return WriteResult(ok=False, written=[], skipped=[summary_relative_path(day)], detail="mind unavailable")

    return sink.write_one(summary_relative_path(day), agenda.daily_summary(day))


def publish_project_daily_summary(
    *,
    service: Optional[AgendaService] = None,
    writer: Optional[MindWriter] = None,
    day: Optional[datetime] = None,
) -> WriteResult:
    """当日日程摘要 → ``Vault/projects/Vaelis/daily/<date>.md``（WP-MIND 写接缝）。

    - 无模型：内容是 ``AgendaService.daily_summary`` 的确定性渲染，真源
      仍是 agenda.db（SQLite，ADR-0007），Mind 里只是当日快照；
    - 串行：走 MindWriter 服务（锁 + 白名单 + verifier/commit），不并行写；
    - 幂等：同一天重跑覆盖同文件；
    - 失败：返回 ``ok=False``，调用方降级为日志告警，绝不抛异常阻塞主对话。
    """
    rel = project_daily_relative_path(day)
    if not is_safe_relative(rel):  # 防御式断言；Vaelis 大写目录在 SAFE_PREFIXES
        logger.warning("mind: refused project daily summary path %s", rel)
        return WriteResult(ok=False, written=[], skipped=[rel], detail="unsafe path")

    agenda = service or get_service()
    sink = writer or get_writer()
    if not sink.available:
        logger.info("mind: vault not configured; skipping project daily summary")
        return WriteResult(ok=False, written=[], skipped=[rel], detail="mind unavailable")

    result = sink.write_one(rel, agenda.daily_summary(day))
    if not result.ok:
        logger.warning("mind: project daily summary not written: %s", result.detail)
    return result
