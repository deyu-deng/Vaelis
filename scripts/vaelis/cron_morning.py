"""cron no_agent 脚本：每日早报（改动率 + 待批项 + 额度）→ 钉钉（切片 B5）。

由 ``scripts/vaelis/register_butler.py`` 复制到 ``HERMES_HOME/scripts/`` 并注册
为每日 07:30 任务。stdout 为 JSON 结果，进 cron 输出留痕。

默认零 LLM（确定性模板）。设 ``VAELIS_BUTLER_POLISH=1`` 时走 L2 便宜模型改写
（B3 额度池），L1 始终只转发。
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
    from vaelis.butler.report import build_morning, format_morning
    from vaelis.notify import get_notifier

    data = build_morning()
    body = format_morning(data)

    if os.environ.get("VAELIS_BUTLER_POLISH", "").strip() in ("1", "true", "yes"):
        from vaelis.butler.polish import polish

        polished = polish(body)
        if polished:
            body = polished

    notifier = get_notifier()
    sent = False
    if notifier.configured:
        outcome = notifier.send(body)
        sent = outcome.ok
        if not outcome.ok:
            print(json.dumps({"error": f"notify failed: {outcome.detail}"}, ensure_ascii=False))
    else:
        print(json.dumps({"warning": "no notifier configured; morning report not delivered"}, ensure_ascii=False))

    print(json.dumps({"report": data, "body": body, "delivered": sent}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
