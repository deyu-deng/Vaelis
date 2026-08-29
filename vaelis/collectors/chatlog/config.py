"""Collector configuration — whitelist first.

Only conversations the user explicitly names are read at all: not decrypted
into our store, not rule-matched, not sent to a model
(docs/adr/0010-collection-whitelist-privacy-boundary.md).

Config lives in ``$HERMES_HOME/vaelis/chatlog.json``; env vars override for
tests and unusual deployments. No drive letters are hardcoded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:5030"
# Webhook delivers in ~13s; this sweep only exists to catch what it dropped.
# 10 minutes keeps the worst case inside the 15-minute notification SLA
# (docs/adr/0005-incremental-rule-plus-model.md, revision note).
DEFAULT_POLL_MINUTES = 10


def config_path() -> Path:
    override = os.environ.get("VAELIS_CHATLOG_CONFIG", "").strip()
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        root = get_hermes_home() / "vaelis"
    except Exception:
        root = Path.home() / ".hermes" / "vaelis"
    return root / "chatlog.json"


@dataclass
class CollectorConfig:
    base_url: str = DEFAULT_BASE_URL
    # Empty whitelist means "collect nothing" — fail closed, never fail open.
    talkers: list[str] = field(default_factory=list)
    poll_minutes: int = DEFAULT_POLL_MINUTES
    enabled: bool = False

    def allows(self, talker: str) -> bool:
        return bool(talker) and talker in set(self.talkers)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "CollectorConfig":
        target = Path(path) if path else config_path()
        data: dict = {}
        if target.exists():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}

        talkers = data.get("talkers")
        env_talkers = os.environ.get("VAELIS_CHATLOG_TALKERS", "").strip()
        if env_talkers:
            talkers = [t.strip() for t in env_talkers.split(",") if t.strip()]

        return cls(
            base_url=str(
                os.environ.get("VAELIS_CHATLOG_URL")
                or data.get("base_url")
                or DEFAULT_BASE_URL
            ).rstrip("/"),
            talkers=[str(t) for t in talkers] if isinstance(talkers, list) else [],
            poll_minutes=int(data.get("poll_minutes") or DEFAULT_POLL_MINUTES),
            enabled=bool(data.get("enabled", False)),
        )

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path else config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "base_url": self.base_url,
                    "talkers": self.talkers,
                    "poll_minutes": self.poll_minutes,
                    "enabled": self.enabled,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target
