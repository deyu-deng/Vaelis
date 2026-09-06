"""cron no_agent 脚本：每晚 20:00 用已有 events 写次日计划 → 钉钉。

由 ``scripts/vaelis/register_butler.py`` 复制到 ``HERMES_HOME/scripts/`` 并注册
为每日 20:00 任务。stdout 为 JSON 结果，进 cron 输出留痕。

默认零 LLM。设 ``VAELIS_BUTLER_POLISH=1`` 时只把 ``summary`` 一段交给 L2
便宜模型润色，**永不**打 L1。空计划推送必须含「明天没有日程，计划为空」。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    try:
        import vaelis  # noqa: F401

        return
    except ImportError:
        pass

    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    runtime = home / "vaelis" / "runtime.json"
    try:
        code_root = json.loads(runtime.read_text(encoding="utf-8"))["code_root"]
        if code_root and code_root not in sys.path:
            sys.path.insert(0, str(code_root))
    except (OSError, json.JSONDecodeError, KeyError):
        print(json.dumps({"error": f"cannot locate code root via {runtime}"}))
        raise SystemExit(1)


_bootstrap()


def main() -> int:
    from vaelis.agenda.planning import format_evening_plan_text, generate_evening_plan
    from vaelis.notify import get_notifier

    plan = generate_evening_plan()
    summary = plan.summary

    if os.environ.get("VAELIS_BUTLER_POLISH", "").strip() in ("1", "true", "yes"):
        from vaelis.butler.polish import polish

        polished = polish(summary)
        if polished:
            summary = polished

    body = format_evening_plan_text(plan, summary=summary)

    notifier = get_notifier()
    sent = False
    if notifier.configured:
        outcome = notifier.send(body)
        sent = outcome.ok
        if not outcome.ok:
            print(json.dumps({"error": f"notify failed: {outcome.detail}"}, ensure_ascii=False))
    else:
        print(
            json.dumps(
                {"warning": "no notifier configured; evening plan not delivered"},
                ensure_ascii=False,
            )
        )

    print(
        json.dumps(
            {"plan": plan.to_dict(), "body": body, "delivered": sent},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
