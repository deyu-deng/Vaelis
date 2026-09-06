"""Vaelis environment doctor — chatlog / aigw / DingTalk / profile (C line).

One command, three-color table. Exit 0 only when nothing is red.
Does not send DingTalk unless ``--send-test``. Never prints secrets.

    python scripts/vaelis/doctor.py
    python scripts/vaelis/doctor.py --json
    python scripts/vaelis/doctor.py --send-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
AIGW_CONFIG_CANDIDATES = (
    REPO_ROOT / "aigw" / "config.yaml",
    REPO_ROOT / "aigw" / "config.example.yaml",
)
CHATLOG_HEALTH_PATHS = ("/health", "/api/v1/health")
DEFAULT_CHATLOG_URL = "http://127.0.0.1:5030"
DEFAULT_AIGW_PORT = 8000
NORTH_STAR = "vaelis_north_star"

GREEN, YELLOW, RED = "green", "yellow", "red"

# Below this share of active traffic being captured by the collector counts
# as "whitelist is leaking chat" — spec from
# ``Docs/PROMPT-CHATLOG-WHITELIST-REPORT.md`` ("低于 10% 标黄").
# See scripts/vaelis/whitelist_report.py.
WHITELIST_EFFICIENCY_YELLOW = 0.10
WHITELIST_PROPOSAL_FILENAME = "whitelist_proposal.json"
WHITELIST_PROPOSAL_FRESH_HOURS = 36


def hermes_home() -> Path:
    override = (os.environ.get("HERMES_HOME") or "").strip()
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home()
    except Exception:
        return Path.home() / ".hermes"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Never logs values."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def apply_env_files(home: Path | None = None) -> list[str]:
    """Fill missing os.environ from HERMES_HOME/.env then repo .env."""
    loaded: list[str] = []
    for path in ( (home or hermes_home()) / ".env", REPO_ROOT / ".env"):
        parsed = load_env_file(path)
        if not parsed:
            continue
        loaded.append(str(path))
        for key, value in parsed.items():
            if key not in os.environ or not str(os.environ.get(key) or "").strip():
                os.environ[key] = value
    return loaded


def parse_aigw_port(config_text: str) -> int:
    """Read ``server.port`` from aigw YAML without requiring PyYAML."""
    in_server = False
    for raw in config_text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r"^server:\s*$", line):
            in_server = True
            continue
        if in_server and re.match(r"^\S", line):
            in_server = False
        if in_server:
            match = re.match(r"^\s+port:\s*(\d+)\s*$", line)
            if match:
                return int(match.group(1))
    return DEFAULT_AIGW_PORT


def aigw_base_from_env_or_config() -> str:
    for key in ("VAELIS_AIGW_URL", "VAELIS_QUOTA_AIGW_URL"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw.rstrip("/")
    for path in AIGW_CONFIG_CANDIDATES:
        if path.is_file():
            port = parse_aigw_port(path.read_text(encoding="utf-8"))
            return f"http://127.0.0.1:{port}/v1"
    return f"http://127.0.0.1:{DEFAULT_AIGW_PORT}/v1"


def aigw_api_key() -> str:
    return (
        (os.environ.get("AIGW_API_KEY") or os.environ.get("AIGW_KEY") or "sk-local-dev-key").strip()
    )


def http_get_json(url: str, timeout: float = 2.5, headers: dict[str, str] | None = None) -> tuple[int | None, Any]:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            code = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError, TimeoutError):
        return None, None
    try:
        return code, json.loads(body)
    except json.JSONDecodeError:
        return code, body[:200]


def check_chatlog(base_url: str = DEFAULT_CHATLOG_URL) -> dict[str, Any]:
    base = base_url.rstrip("/")
    last_code = None
    for path in CHATLOG_HEALTH_PATHS:
        code, _ = http_get_json(f"{base}{path}")
        last_code = code
        if code == 200:
            return {
                "id": "chatlog",
                "color": GREEN,
                "detail": f"{base}{path} ok",
            }
    if last_code is None:
        return {
            "id": "chatlog",
            "color": RED,
            "detail": f"{base} unreachable — start scripts/chatlog_server.ps1 (WeChat login + CHATLOG_DATA_KEY)",
        }
    return {
        "id": "chatlog",
        "color": RED,
        "detail": f"{base} HTTP {last_code}",
    }


def check_aigw(base_url: str | None = None) -> dict[str, Any]:
    base = (base_url or aigw_base_from_env_or_config()).rstrip("/")
    models_url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    code, payload = http_get_json(
        models_url,
        headers={"Authorization": f"Bearer {aigw_api_key()}"},
    )
    if code != 200 or payload is None:
        return {
            "id": "aigw",
            "color": RED,
            "detail": f"{models_url} down — run scripts/vaelis/aigw_start.ps1",
            "url": models_url,
        }
    names: list[str] = []
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("models") or []
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and row.get("id"):
                    names.append(str(row["id"]))
                elif isinstance(row, str):
                    names.append(row)
    has_workbuddy = any(name.startswith("workbuddy/") for name in names)
    color = GREEN if has_workbuddy else YELLOW
    detail = f"{models_url} {len(names)} models"
    if has_workbuddy:
        detail += "; workbuddy/* present"
    elif names:
        detail += "; no workbuddy/* yet (mock ok for wiring)"
    else:
        detail += "; empty catalog"
    return {
        "id": "aigw",
        "color": color,
        "detail": detail,
        "url": models_url,
        "models": names[:20],
    }


def check_dingtalk() -> dict[str, Any]:
    url = (os.environ.get("DINGTALK_WEBHOOK_URL") or "").strip()
    secret = (os.environ.get("DINGTALK_WEBHOOK_SECRET") or "").strip()
    if not url:
        return {
            "id": "dingtalk",
            "color": RED,
            "detail": "DINGTALK_WEBHOOK_URL missing — add to HERMES_HOME/.env or Code/.env (never commit)",
        }
    if not secret:
        return {
            "id": "dingtalk",
            "color": YELLOW,
            "detail": "webhook set, DINGTALK_WEBHOOK_SECRET empty (加签 robots will reject)",
        }
    return {
        "id": "dingtalk",
        "color": GREEN,
        "detail": "DINGTALK_WEBHOOK_URL + SECRET present (not sent)",
    }


def soul_has_routing_block(soul: str) -> bool:
    """True if SOUL has L1 routing fence (old HTML or :::VAELIS_L1_ASK_ROUTING:::)."""
    return "VAELIS_L1" in (soul or "")


def _toolsets_from_config(cfg: dict) -> set[str]:
    found: set[str] = set()
    top = cfg.get("toolsets") or []
    if isinstance(top, list):
        found.update(str(item) for item in top)
    platforms = cfg.get("platform_toolsets") or {}
    if isinstance(platforms, dict):
        for key in ("cli", "gateway"):
            listed = platforms.get(key) or []
            if isinstance(listed, list):
                found.update(str(item) for item in listed)
    plugins = cfg.get("plugins") or {}
    if isinstance(plugins, dict):
        enabled = plugins.get("enabled") or []
        if isinstance(enabled, list) and "vaelis-north-star" in enabled:
            found.add(NORTH_STAR)
    return found


def check_north_star(home: Path | None = None) -> dict[str, Any]:
    root = home or hermes_home()
    cfg_path = root / "config.yaml"
    if not cfg_path.is_file():
        return {
            "id": "north_star",
            "color": RED,
            "detail": f"no {cfg_path}",
        }
    try:
        import yaml

        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {
            "id": "north_star",
            "color": RED,
            "detail": f"cannot parse {cfg_path}: {exc}",
        }
    if not isinstance(cfg, dict):
        cfg = {}
    names = _toolsets_from_config(cfg)
    soul = (root / "SOUL.md").read_text(encoding="utf-8") if (root / "SOUL.md").is_file() else ""
    has_block = soul_has_routing_block(soul)
    if NORTH_STAR in names and has_block:
        color, extra = GREEN, "toolset + SOUL routing block"
    elif NORTH_STAR in names:
        color, extra = YELLOW, "toolset on, SOUL routing block missing"
    else:
        color, extra = RED, "vaelis_north_star not in toolsets/cli/gateway"
    return {
        "id": "north_star",
        "color": color,
        "detail": f"{cfg_path}: {extra}",
        "toolsets": sorted(names),
    }


def check_chatlog_config(home: Path | None = None) -> dict[str, Any]:
    root = home or hermes_home()
    path = root / "vaelis" / "chatlog.json"
    if not path.is_file():
        return {
            "id": "collect",
            "color": RED,
            "detail": f"{path} missing — first-run blacklist review not done",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"id": "collect", "color": RED, "detail": f"{path} unreadable: {exc}"}
    if not isinstance(data, dict):
        return {"id": "collect", "color": RED, "detail": f"{path} not an object"}
    mode = str(data.get("mode") or "").strip().lower()
    talkers = data.get("talkers") or []
    blacklist = data.get("blacklist") or []
    enabled = data.get("enabled", True)
    collectable = mode == "blacklist" and (isinstance(talkers, list) or True)
    if mode != "blacklist":
        return {
            "id": "collect",
            "color": RED,
            "detail": f"{path} mode={mode or 'unset'} (want blacklist)",
        }
    if enabled is False:
        return {
            "id": "collect",
            "color": YELLOW,
            "detail": f"{path} blacklist but enabled=false",
        }
    extra = f"talkers={len(talkers) if isinstance(talkers, list) else 0} excluded={len(blacklist) if isinstance(blacklist, list) else 0}"
    return {
        "id": "collect",
        "color": GREEN if collectable else YELLOW,
        "detail": f"{path} blacklist {extra}",
    }


def _whitelist_proposal_path(home: Path | None = None) -> Path:
    """Where ``whitelist_report.py`` writes the proposal JSON.

    Honours ``VAELIS_CHATLOG_CONFIG`` (per-file override) the same way the
    collector's :func:`config_path` does, so this never points at the wrong
    ``HERMES_HOME`` when the operator has pinned chatlog.json elsewhere.
    """
    override = (os.environ.get("VAELIS_CHATLOG_CONFIG") or "").strip()
    if override:
        return Path(override).parent / WHITELIST_PROPOSAL_FILENAME
    return (home or hermes_home()) / "vaelis" / WHITELIST_PROPOSAL_FILENAME


def _read_proposal_age_hours(path: Path) -> float | None:
    """Return age in hours of the proposal file, or None if unparseable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stamp = str(data.get("generated_at") or "").strip()
        if not stamp:
            return None
        # Proposal timestamps are ISO-8601 in UTC ("...+00:00" or trailing "Z").
        cleaned = stamp.replace("Z", "+00:00")
        generated = datetime.fromisoformat(cleaned)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - generated).total_seconds() / 3600.0
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def check_chatlog_whitelist_efficiency(home: Path | None = None) -> dict[str, Any]:
    """Reads ``whitelist_proposal.json`` (last sweep) to flag a leaky whitelist.

    The ratio we surface is the share of *active* chatlog talkers that the
    current whitelist (or known set, in blacklist mode) does not capture.
    Anything below :data:`WHITELIST_EFFICIENCY_YELLOW` means most of the
    recent chat traffic is invisible to the collector and the morning brief
    will keep reporting "honest empty".
    """
    proposal_path_value = _whitelist_proposal_path(home)
    if not proposal_path_value.is_file():
        return {
            "id": "whitelist_eff",
            "color": YELLOW,
            "detail": (
                f"no {proposal_path_value} — run scripts/vaelis/whitelist_report.py to seed it"
            ),
        }
    try:
        data = json.loads(proposal_path_value.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "id": "whitelist_eff",
            "color": RED,
            "detail": f"{proposal_path_value} unreadable: {exc}",
        }
    if not isinstance(data, dict):
        return {
            "id": "whitelist_eff",
            "color": RED,
            "detail": f"{proposal_path_value} malformed JSON",
        }
    topn = data.get("topn") or []
    if not isinstance(topn, list) or not topn:
        return {
            "id": "whitelist_eff",
            "color": YELLOW,
            "detail": f"{proposal_path_value} has no topn data — re-run whitelist_report.py",
        }

    # The right "is the collector capturing this?" signal depends on the mode
    # the proposal was generated under:
    #   * whitelist — ``in_current_whitelist`` is the gate; False == refused.
    #   * blacklist  — ``in_blacklist`` is the gate; True  == refused.
    # Anything else (no flag set) is treated as not-captured so an unknown
    # proposal shape fails loud rather than silently going green.
    proposal_mode = str(data.get("mode") or "").strip().lower()

    def _is_captured(row: dict[str, Any]) -> bool:
        if proposal_mode == "blacklist":
            return not bool(row.get("in_blacklist"))
        if proposal_mode == "whitelist":
            return bool(row.get("in_current_whitelist"))
        return False

    def _is_refused(row: dict[str, Any]) -> bool:
        if proposal_mode == "blacklist":
            return bool(row.get("in_blacklist"))
        if proposal_mode == "whitelist":
            return not bool(row.get("in_current_whitelist"))
        return True

    captured = sum(1 for row in topn if isinstance(row, dict) and _is_captured(row))
    total = len(topn)
    active_total = int(data.get("active_talkers_total") or 0)
    refused_sample = [
        row.get("talker") for row in topn
        if isinstance(row, dict) and _is_refused(row)
    ][:5]

    # If the proposal is older than the freshness window, treat it as stale —
    # the user may have added more talkers since the snapshot.
    age_hours = _read_proposal_age_hours(proposal_path_value)
    if age_hours is not None and age_hours > WHITELIST_PROPOSAL_FRESH_HOURS:
        return {
            "id": "whitelist_eff",
            "color": YELLOW,
            "detail": (
                f"captured={captured}/{total} of top active traffic "
                f"(active_talkers={active_total}); proposal stale ({age_hours:.1f}h old, "
                f"threshold {WHITELIST_PROPOSAL_FRESH_HOURS}h) — re-run whitelist_report.py"
            ),
        }

    if total == 0:
        return {"id": "whitelist_eff", "color": YELLOW, "detail": "no topn rows"}

    capture_ratio = captured / total
    shortlist = ", ".join(str(t) for t in refused_sample if t)
    detail = (
        f"captured={captured}/{total} of top active traffic "
        f"(active_talkers={active_total}, mode={proposal_mode or '?'}, "
        f"window_hours={data.get('window_hours', '?')})"
    )
    if shortlist:
        detail += f"; top refused: {shortlist}"

    if capture_ratio < WHITELIST_EFFICIENCY_YELLOW:
        return {
            "id": "whitelist_eff",
            "color": YELLOW,
            "detail": (
                f"{detail} — gate is dropping (below "
                f"{int(WHITELIST_EFFICIENCY_YELLOW * 100)}% threshold); "
                "review config (mode/whitelist/blacklist) and re-run whitelist_report.py"
            ),
        }
    return {"id": "whitelist_eff", "color": GREEN, "detail": detail}


def send_dingtalk_test() -> dict[str, Any]:
    try:
        from vaelis.notify.dingtalk import DingTalkNotifier
    except Exception as exc:
        return {"id": "dingtalk_send", "color": RED, "detail": f"import failed: {exc}"}
    outcome = DingTalkNotifier().send("Vaelis doctor --send-test")
    return {
        "id": "dingtalk_send",
        "color": GREEN if outcome.ok else RED,
        "detail": outcome.detail if hasattr(outcome, "detail") else str(outcome),
    }


def run_checks(*, send_test: bool = False) -> list[dict[str, Any]]:
    apply_env_files()
    rows = [
        check_chatlog(),
        check_aigw(),
        check_dingtalk(),
        check_north_star(),
        check_chatlog_config(),
        check_chatlog_whitelist_efficiency(),
    ]
    if send_test:
        rows.append(send_dingtalk_test())
    return rows


def worst_exit(rows: list[dict[str, Any]]) -> int:
    if any(row.get("color") == RED for row in rows):
        return 1
    return 0


def format_table(rows: list[dict[str, Any]]) -> str:
    lines = [f"{'id':<14} {'color':<8} detail", "-" * 72]
    for row in rows:
        lines.append(f"{row.get('id', ''):<14} {row.get('color', ''):<8} {row.get('detail', '')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vaelis env doctor")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--send-test", action="store_true", help="actually POST a DingTalk test card")
    args = parser.parse_args(argv)
    rows = run_checks(send_test=args.send_test)
    if args.json:
        print(json.dumps({"hermes_home": str(hermes_home()), "checks": rows}, ensure_ascii=False, indent=2))
    else:
        print(f"HERMES_HOME={hermes_home()}")
        print(format_table(rows))
        parsed = urlparse(aigw_base_from_env_or_config())
        print(f"aigw probe host={parsed.hostname} port={parsed.port or DEFAULT_AIGW_PORT}")
    return worst_exit(rows)


if __name__ == "__main__":
    sys.exit(main())
