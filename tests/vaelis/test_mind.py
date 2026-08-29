"""Mind access: path safety, serialization, verifier gate, narrow reads."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pytest

from vaelis.agenda.mind_sync import publish_daily_summary, summary_relative_path
from vaelis.agenda.service import AgendaService
from vaelis.mind import paths
from vaelis.mind.lock import MindLockTimeout, mind_write_lock
from vaelis.mind.paths import UnsafeMindPath, is_safe_relative, resolve_root, safe_target
from vaelis.mind.reader import MindReader
from vaelis.mind.writer import MindWriter, WriteRequest


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    root = tmp_path / "Mind"
    (root / "Vault" / "meta").mkdir(parents=True)
    (root / "Vault" / "projects" / "vaelis").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Mind", encoding="utf-8")
    (root / "Vault" / "meta" / "Persona.md").write_text("我是邓德宇。", encoding="utf-8")
    (root / "Vault" / "projects" / "vaelis" / "plan.md").write_text("# Vaelis\n北极星…", encoding="utf-8")
    (root / "Vault" / "projects" / "vaelis" / "progress.md").write_text("M1 进行中", encoding="utf-8")
    monkeypatch.setenv("MIND_ROOT", str(root))
    return root


# --- path safety ------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "Loom/raw/chat-logs/digested/2026-08-25/agenda.md",
        "Vault/projects/vaelis/notes.md",
        "Vault/inbox/idea.md",
    ],
)
def test_safe_paths_are_accepted(relative):
    assert is_safe_relative(relative) is True


@pytest.mark.parametrize(
    "relative",
    [
        "AGENTS.md",                       # would rewrite Mind's own contract
        "Vault/projects/新项目/plan.md",    # new project dir trips the verifier
        "Loom/skills/whatever/SKILL.md",   # skill count declaration
        "../outside.md",
        "/etc/passwd",
        "",
    ],
)
def test_unsafe_paths_are_refused(relative):
    assert is_safe_relative(relative) is False


def test_safe_target_rejects_traversal(vault):
    with pytest.raises(UnsafeMindPath):
        safe_target(vault, "Vault/inbox/../../../escape.md")


def test_resolve_root_prefers_env(vault, monkeypatch, tmp_path):
    assert resolve_root() == vault

    monkeypatch.setenv("MIND_ROOT", str(tmp_path / "nowhere"))
    assert resolve_root() is None


def test_no_hardcoded_drive_letters_in_paths_module():
    source = Path(paths.__file__ or "")
    text = source.read_text(encoding="utf-8")
    assert "D:/Mind" not in text
    assert "/Users/ciel" not in text


# --- writer -----------------------------------------------------------------


def test_write_lands_under_loom(vault):
    writer = MindWriter(vault, run_verifier=False)
    result = writer.write_one("Loom/raw/chat-logs/digested/2026-08-25/agenda.md", "# 摘要\n")

    assert result.ok is True
    assert (vault / "Loom/raw/chat-logs/digested/2026-08-25/agenda.md").read_text(encoding="utf-8") == "# 摘要\n"


def test_unsafe_write_is_skipped_not_fatal(vault):
    writer = MindWriter(vault, run_verifier=False)
    result = writer.write(
        [
            WriteRequest("AGENTS.md", "hijacked"),
            WriteRequest("Vault/inbox/ok.md", "fine"),
        ]
    )

    assert result.ok is True
    assert result.skipped == ["AGENTS.md"]
    assert (vault / "AGENTS.md").read_text(encoding="utf-8") == "# Mind"


def test_append_mode_accumulates(vault):
    writer = MindWriter(vault, run_verifier=False)
    writer.write_one("Vault/inbox/log.md", "one\n", mode="append")
    writer.write_one("Vault/inbox/log.md", "two\n", mode="append")

    assert (vault / "Vault/inbox/log.md").read_text(encoding="utf-8") == "one\ntwo\n"


def test_writer_reports_when_vault_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MIND_ROOT", str(tmp_path / "absent"))
    writer = MindWriter(run_verifier=False)

    assert writer.available is False
    result = writer.write_one("Vault/inbox/x.md", "x")
    assert result.ok is False
    assert result.written == []


def test_failing_verifier_blocks_the_commit_but_keeps_files(vault):
    scripts = vault / "Loom" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "verifier.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")

    writer = MindWriter(vault, run_verifier=True)
    result = writer.write_one("Vault/inbox/x.md", "x")

    assert result.ok is False
    assert "verifier" in result.detail
    # The file is still written — Mind is a working copy, not a transaction.
    assert (vault / "Vault/inbox/x.md").exists()


def test_passing_verifier_allows_the_write(vault):
    scripts = vault / "Loom" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "verifier.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    result = MindWriter(vault, run_verifier=True).write_one("Vault/inbox/x.md", "x")
    assert result.ok is True


def test_missing_verifier_is_not_a_blocker(vault):
    assert MindWriter(vault, run_verifier=True).write_one("Vault/inbox/x.md", "x").ok is True


def test_concurrent_writers_do_not_interleave(vault):
    writer = MindWriter(vault, run_verifier=False)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            writer.write_one(f"Vault/inbox/w{index}.md", f"content {index}")
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    for index in range(8):
        assert (vault / f"Vault/inbox/w{index}.md").read_text(encoding="utf-8") == f"content {index}"
    # The lock file must not survive the batch.
    assert not (vault / ".vaelis-mind.lock").exists()


def test_lock_times_out_rather_than_hanging(tmp_path):
    lock_path = tmp_path / "held.lock"
    with mind_write_lock(lock_path, timeout=1.0):
        with pytest.raises(MindLockTimeout):
            with mind_write_lock(lock_path, timeout=0.2):
                pass


def test_writer_never_imports_a_model_client():
    from vaelis.mind import writer as writer_module

    text = Path(writer_module.__file__ or "").read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "deepseek", "completion("):
        assert forbidden not in text


# --- reader -----------------------------------------------------------------


def test_reader_pulls_persona_and_projects(vault):
    context = MindReader(vault).context()

    assert "邓德宇" in context.persona
    assert [p.name for p in context.projects] == ["vaelis"]
    assert "北极星" in context.projects[0].plan_excerpt
    assert "M1" in context.projects[0].progress_excerpt


def test_reader_excerpts_are_capped(vault):
    huge = "字" * 50_000
    (vault / "Vault" / "meta" / "Persona.md").write_text(huge, encoding="utf-8")

    persona = MindReader(vault).persona()
    assert len(persona) < 5_000


def test_reader_is_quiet_when_vault_absent(tmp_path):
    reader = MindReader(tmp_path / "absent")

    assert reader.available is False
    assert reader.persona() == ""
    assert reader.projects() == []
    assert reader.context().is_empty is True


def test_reader_skips_empty_project_dirs(vault):
    (vault / "Vault" / "projects" / "empty").mkdir()
    assert [p.name for p in MindReader(vault).projects()] == ["vaelis"]


# --- agenda digest ----------------------------------------------------------


def test_daily_summary_is_published_under_loom(vault, tmp_path):
    service = AgendaService(tmp_path / "agenda.db")
    today = datetime.now()
    service.create_manual(title="组会", start_at=today.replace(hour=15, minute=0, second=0, microsecond=0))

    result = publish_daily_summary(service=service, writer=MindWriter(vault, run_verifier=False))

    assert result.ok is True
    written = vault / summary_relative_path()
    assert written.is_file()
    assert "组会" in written.read_text(encoding="utf-8")


def test_daily_summary_is_idempotent(vault, tmp_path):
    service = AgendaService(tmp_path / "agenda.db")
    writer = MindWriter(vault, run_verifier=False)

    publish_daily_summary(service=service, writer=writer)
    publish_daily_summary(service=service, writer=writer)

    body = (vault / summary_relative_path()).read_text(encoding="utf-8")
    assert body.count("# 日程摘要") == 1


def test_daily_summary_without_vault_is_a_soft_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("MIND_ROOT", str(tmp_path / "absent"))
    service = AgendaService(tmp_path / "agenda.db")

    result = publish_daily_summary(service=service, writer=MindWriter(run_verifier=False))
    assert result.ok is False
    assert "unavailable" in result.detail
