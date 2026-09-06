"""B2: L2 常驻 Agent 注册表 — registry round-trip / routing 断言 / spawn。

注册表 = $HERMES_HOME/vaelis/projects.yaml（profile-safe）；spawn 落地 profile
（复用 hermes_cli.profiles.create_profile）+ 写 profile 级 vaelis/models.json
（ADR-0011 断言绿）+ 同步 config.yaml 模型。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from vaelis.agents.registry import AgentEntry, AgentRegistry, RegistryError, default_path


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """隔离 HERMES_HOME + Path.home()（run_tests.sh 的 env -i 丢 USERPROFILE）。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.delenv("VAELIS_MODELS_CONFIG", raising=False)
    monkeypatch.delenv("VAELIS_PROJECTS_CONFIG", raising=False)
    return tmp_path


def _entry(**kw):
    defaults = dict(name="agenda", role="l2_agenda", model="deepseek-chat")
    defaults.update(kw)
    return AgentEntry(**defaults)


# ---------------------------------------------------------------------------
# default_path & IO
# ---------------------------------------------------------------------------


def test_default_path_is_hermes_home_anchored(home):
    assert default_path() == Path(home) / ".hermes" / "vaelis" / "projects.yaml"


def test_load_missing_returns_empty(home):
    reg = AgentRegistry.load()
    assert reg.agents == {}
    assert reg.path == default_path()


def test_round_trip_preserves_entries(home):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="agenda", skills=("a", "b"), description="日程闭环"))
    reg.upsert(_entry(name="srtp", role="l2_project", profile="l2-srtp"))
    path = reg.save()

    assert path.is_file()
    reloaded = AgentRegistry.load(path)
    assert set(reloaded.names()) == {"agenda", "srtp"}
    assert reloaded.get("agenda").skills == ("a", "b")
    assert reloaded.get("agenda").description == "日程闭环"
    assert reloaded.get("srtp").profile_name == "l2-srtp"


def test_missing_profile_field_falls_back_to_name(home):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="x", profile=""))
    assert reg.get("x").profile_name == "x"


# ---------------------------------------------------------------------------
# routing 断言（ADR-0011：L1≠L2，L1 不得 GUI-only）
# ---------------------------------------------------------------------------


def test_registry_with_l1_and_l2_is_green(home):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="secretary", role="l1_secretary", provider="moonshot", model="kimi-k3"))
    reg.upsert(_entry(name="agenda", role="l2_agenda", model="deepseek-chat"))
    assert reg.routing_problems() == []


def test_l2_sharing_l1_model_is_flagged(home):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="secretary", role="l1_secretary", provider="moonshot", model="kimi-k3"))
    reg.upsert(_entry(name="bad", role="l2_agenda", provider="moonshot", model="kimi-k3"))
    problems = reg.routing_problems()
    assert any("shares L1" in p for p in problems)


def test_upsert_removes_and_round_trips(home):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="agenda"))
    assert reg.remove("agenda") is True
    assert reg.remove("nope") is False


# ---------------------------------------------------------------------------
# spawn
# ---------------------------------------------------------------------------


@pytest.fixture()
def spawn_env(home, monkeypatch):
    """把 spawn 的 create_profile 缩到最小：只 mkdir，不碰真实 profile 逻辑。

    spawn 在测试里必须验证 profile 目录 + models.json + config.yaml 三个产物。
    create_profile 会走 seed skills / clone 等重逻辑，直接替换成 mkdir 即可。
    """
    import hermes_cli.profiles as profiles_mod

    def fake_create_profile(name, **kwargs):
        profile_dir = Path(home) / ".hermes" / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "vaelis").mkdir(exist_ok=True)
        (profile_dir / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        return profile_dir

    def fake_profile_exists(name):
        return (Path(home) / ".hermes" / "profiles" / name).is_dir()

    monkeypatch.setattr(profiles_mod, "create_profile", fake_create_profile)
    monkeypatch.setattr(profiles_mod, "profile_exists", fake_profile_exists)
    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create_profile)
    monkeypatch.setattr("hermes_cli.profiles.profile_exists", fake_profile_exists)
    return home


def test_spawn_creates_profile_and_models(spawn_env):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="secretary", role="l1_secretary", provider="moonshot", model="kimi-k3"))
    reg.upsert(_entry(name="agenda", role="l2_agenda", provider="deepseek", model="deepseek-chat"))
    reg.save()

    result = reg.spawn("agenda")

    assert result["routing_ok"] is True
    profile_dir = Path(result["profile_dir"])
    assert profile_dir.is_dir()
    models = json.loads((profile_dir / "vaelis" / "models.json").read_text(encoding="utf-8"))
    assert models["roles"]["l2_agenda"]["provider"] == "deepseek"
    assert models["roles"]["l2_agenda"]["model"] == "deepseek-chat"
    # ADR-0011：写进 profile 的路由表断言绿（L1≠L2）
    from vaelis.routing import ModelRouter

    assert ModelRouter.load(profile_dir / "vaelis" / "models.json").violations() == []
    # config.yaml 同步了模型
    cfg = (profile_dir / "config.yaml").read_text(encoding="utf-8")
    assert "deepseek-chat" in cfg


def test_spawn_routing_violation_aborts(spawn_env):
    reg = AgentRegistry.load()
    # L1 缺失 → spawn 时 profile 路由表断言失败
    reg.upsert(_entry(name="agenda", role="l2_agenda", provider="moonshot", model="kimi-k3"))
    reg.save()

    with pytest.raises(RegistryError, match="routing"):
        reg.spawn("agenda")


def test_spawn_unknown_agent_raises(home):
    reg = AgentRegistry.load()
    with pytest.raises(RegistryError, match="not registered"):
        reg.spawn("nope")


def test_spawn_reuses_existing_profile(spawn_env):
    reg = AgentRegistry.load()
    reg.upsert(_entry(name="secretary", role="l1_secretary", provider="moonshot", model="kimi-k3"))
    reg.upsert(_entry(name="agenda", role="l2_agenda", provider="deepseek", model="deepseek-chat"))
    reg.save()

    reg.spawn("agenda")
    # 第二次 spawn：profile 已存在，仍成功且复用同一目录
    result2 = reg.spawn("agenda")
    assert result2["routing_ok"] is True


# ---------------------------------------------------------------------------
# CLI（薄壳）冒烟
# ---------------------------------------------------------------------------


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        for attr in ("role", "profile", "provider", "model", "mind_subtree", "skills", "description", "clone_from", "registry"):
            if attr not in self.__dict__:
                self.__dict__[attr] = None


def test_cli_list_empty(home, capsys):
    from vaelis.agents.cli import run_vaelis

    run_vaelis(_Args(vaelis_action="agents", agents_action="list"))
    out = capsys.readouterr().out
    assert "No resident agents registered" in out


def test_cli_register_then_spawn(spawn_env, capsys, monkeypatch):
    from vaelis.agents import cli

    run_vaelis = cli.run_vaelis

    run_vaelis(_Args(
        vaelis_action="agents", agents_action="register", name="secretary",
        role="l1_secretary", profile="master", provider="moonshot", model="kimi-k3",
    ))
    run_vaelis(_Args(
        vaelis_action="agents", agents_action="register", name="agenda",
        role="l2_agenda", provider="deepseek", model="deepseek-chat",
    ))

    run_vaelis(_Args(vaelis_action="agents", agents_action="spawn", name="agenda"))
    out = capsys.readouterr().out
    assert "Spawned agenda" in out
    assert "hermes -p agenda chat" in out
    # 落盘后注册表可见
    reg = AgentRegistry.load()
    assert set(reg.names()) == {"agenda", "secretary"}


def test_cli_spawn_inline_register(spawn_env, capsys):
    """spawn 未注册的 agent 且带 --role/--model → 自动注册再 spawn。"""
    from vaelis.agents.cli import run_vaelis

    run_vaelis(_Args(
        vaelis_action="agents", agents_action="spawn", name="secretary",
        role="l1_secretary", profile="master", provider="moonshot", model="kimi-k3",
    ))
    run_vaelis(_Args(
        vaelis_action="agents", agents_action="spawn", name="agenda",
        role="l2_agenda", provider="deepseek", model="deepseek-chat",
    ))
    out = capsys.readouterr().out
    assert "Spawned agenda" in out
    assert "ADR-0011 green" in out


# --------------------------------------------------------------------------- #
# C5 pace field (weekly_hours) on l2_project entries
# --------------------------------------------------------------------------- #


def test_pace_roundtrip_and_weekly_hours():
    entry = AgentEntry.from_dict("sim", {"role": "l2_project", "pace": {"weekly_hours": 6}})
    assert entry.weekly_hours == 6.0
    data = entry.to_dict()
    assert data["pace"] == {"weekly_hours": 6.0}
    clone = AgentEntry.from_dict("sim", data)
    assert clone.weekly_hours == 6.0


def test_pace_defaults_to_none():
    entry = AgentEntry.from_dict("sim", {"role": "l2_project"})
    assert entry.pace is None
    assert entry.weekly_hours is None
    assert "pace" not in entry.to_dict()


def test_pace_rejects_bad_values():
    with pytest.raises(RegistryError):
        AgentEntry.from_dict("sim", {"role": "l2_project", "pace": {"weekly_hours": 0}})
    with pytest.raises(RegistryError):
        AgentEntry.from_dict("sim", {"role": "l2_project", "pace": {"weekly_hours": -3}})
    with pytest.raises(RegistryError):
        AgentEntry.from_dict("sim", {"role": "l2_project", "pace": {"weekly_hours": 200}})
    with pytest.raises(RegistryError):
        AgentEntry.from_dict("sim", {"role": "l2_project", "pace": {"weekly_hours": "abc"}})


def test_registry_roundtrip_preserves_pace(home):
    registry = AgentRegistry(path=home / "projects.yaml")
    registry.upsert(AgentEntry.from_dict("sim", {"role": "l2_project", "pace": {"weekly_hours": 6}}))
    registry.save()
    reloaded = AgentRegistry.load(home / "projects.yaml")
    assert reloaded.get("sim").weekly_hours == 6.0
