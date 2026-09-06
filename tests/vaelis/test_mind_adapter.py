"""WP-MIND 窄切适配：MindProvider 读/写接缝 + mind_sync Vault 子树通道。

对照 MIND_ADAPTER_PLAN.md（Docs/）与任务书验收：
1. 读接缝——prefetch 召回带画像/项目状态摘要（日志可证，失败降级）；
2. 写接缝——每日日程摘要经 mind_sync → Vault/projects/Vaelis/daily/，
   无模型、串行 MindWriter、幂等；写失败只告警不阻塞主对话流。
3. 边界——运行时状态真源仍是 SQLite（ADR-0007）；非 primary 上下文不写。
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import pytest

from vaelis.agenda import store


def _load_provider_module():
    """plugins/ 目录按文件路径加载（不触发包级发现副作用）。"""
    path = (
        Path(__file__).resolve().parents[2]
        / "plugins" / "memory" / "mind" / "mind.py"
    )
    spec = importlib.util.spec_from_file_location("mind_provider_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIND_MOD = _load_provider_module()


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    """临时 Mind vault：persona + 大写 Vaelis 项目（当前写入位）。"""
    root = tmp_path / "Mind"
    (root / "Vault" / "meta").mkdir(parents=True)
    (root / "Vault" / "projects" / "Vaelis").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Mind", encoding="utf-8")
    (root / "Vault" / "meta" / "Persona.md").write_text(
        "我是小龟，浙大本科生。", encoding="utf-8"
    )
    (root / "Vault" / "projects" / "Vaelis" / "plan.md").write_text(
        "# Vaelis\n北极星：人只负责审核和提想法。", encoding="utf-8"
    )
    (root / "Vault" / "projects" / "Vaelis" / "progress.md").write_text(
        "M1 推进中，Wave B 完成。", encoding="utf-8"
    )
    monkeypatch.setattr(MIND_MOD, "_resolve_root", lambda: root)
    return root


@pytest.fixture()
def provider():
    return MIND_MOD.MindProvider()


# ── 接缝 1：读——召回带画像摘要 ───────────────────────────────────────────────


def test_prefetch_includes_profile_summary(vault, provider, caplog):
    with caplog.at_level(logging.INFO, logger=MIND_MOD.__name__):
        result = provider.prefetch("随便问点什么")
    assert "[Mind 画像]" in result
    assert "我是小龟" in result
    assert "### 项目 Vaelis" in result
    assert "M1 推进中" in result
    # 验收 2：画像读取路径生效，日志可证
    assert any("prefetch includes profile summary" in r.message for r in caplog.records)


def test_prefetch_profile_read_failure_is_non_fatal(vault, provider, caplog, monkeypatch):
    def boom(root):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(MIND_MOD, "_profile_block", boom)
    with caplog.at_level(logging.WARNING, logger=MIND_MOD.__name__):
        result = provider.prefetch("查询")
    assert "Mind 画像" not in result  # 降级为无画像，不抛异常
    assert any("profile summary read failed" in r.message for r in caplog.records)


def test_prefetch_without_vault_returns_empty(provider, monkeypatch):
    monkeypatch.setattr(
        MIND_MOD, "_resolve_root", lambda: Path("mind-root-not-configured")
    )
    assert provider.prefetch("查询") == ""


def test_profile_block_is_bounded(tmp_path, monkeypatch):
    root = tmp_path / "Mind"
    (root / "Vault" / "meta").mkdir(parents=True)
    (root / "Vault" / "projects" / "Vaelis").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Mind", encoding="utf-8")
    (root / "Vault" / "meta" / "Persona.md").write_text("p" * 5000, encoding="utf-8")
    (root / "Vault" / "projects" / "Vaelis" / "plan.md").write_text("q" * 5000, encoding="utf-8")
    block = MIND_MOD._profile_block(root)
    assert len(block) < 3000  # 每段 800 截断，窄切不淹上下文
    assert "…" in block
