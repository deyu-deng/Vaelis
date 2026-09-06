"""Mind memory provider — Vaelis ↔ Mind second-brain vault adapter.

============================================================================
STATUS: IMPLEMENTED (P0).
============================================================================
This file wires ``MindProvider`` to the ``MemoryProvider`` ABC so the plugin
is discoverable, loadable, and activatable by Vaelis. P0 implements the real
disk I/O for every lifecycle method while respecting the compliance boundary
below. All writes funnel through :class:`vaelis.mind.writer.MindWriter`
(serialized + verifier + commit switch) and are pre-checked with ``_is_safe``.

Full spec + evidence:  docs/specs/MIND_ADAPTER_PLAN.md  (repo root)
Mind repo (official):  ``mind/`` (lowercase, inside the repository;
                       env ``MIND_ROOT`` overrides — never hardcode drive letters)
Mind verifier:         Loom/scripts/verifier.py (inside the Mind repo)

Why a plugin and not core changes?
  Vaelis memory is provider-pluginized (AGENTS.md: "capability at the edges").
  Adding ``plugins/memory/mind/`` + setting ``memory.provider: mind`` in
  config.yaml is the *only* integration step — agent/memory_provider.py,
  memory_manager.py, and run_agent.py are NOT touched.  (Verified 2026-07-13.)

Compliance boundary (CRITICAL — see plan §3/§5):
  Mind's git pre-commit verifier BLOCKS commits where:
    (1) Vault/projects top-level dir names != AGENTS.md §1 declaration, OR
    (2) Loom/skills skill count != AGENTS.md declaration.
  All REAL writes must stay inside SAFE_PREFIXES below. Writing elsewhere
  (new top-level project dir, new skill dir, AGENTS.md edits) risks BLOCKING
  Mind's commits or polluting the second brain. When implementing, assert the
  resolved path is under a SAFE_PREFIX before any write.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from vaelis.mind.paths import SAFE_PREFIXES
from vaelis.mind.writer import MindWriter

logger = logging.getLogger(__name__)

# --- Compliance boundary -------------------------------------------------
# Real writes MUST resolve under one of these relative prefixes (relative to
# MIND_ROOT). These are the zones Mind's verifier does NOT block. Do not add
# Vault/projects/<new> or Loom/skills/<new> here — those require editing Mind's
# own AGENTS.md declarations, which this plugin must never do automatically.
# NOTE: the Vaelis project zone is the official capitalised ``Vaelis`` dir —
# the lowercase ``vaelis`` dir is a legacy Plobi archive and must never be
# created by accident (writing there would pollute the knowledge base).
# SAFE_PREFIXES is imported from vaelis.mind.paths — the single source of
# truth. Do NOT redefine it here; updating one without the other causes
# security checks to diverge.

MAX_DIGEST_TURNS = 40
MAX_DIGEST_CHARS_PER_MSG = 1200


def _resolve_root() -> Path:
    """Resolve the Mind root.

    Delegates to :mod:`vaelis.mind.paths` so there is one resolver and no
    hardcoded drive letters (the North Star contract requires ``MIND_ROOT``).
    Returns a non-existent placeholder when nothing is configured, so callers
    can keep using ``.is_dir()`` as the availability check.
    """
    from vaelis.mind.paths import resolve_root as _shared_resolve

    root = _shared_resolve()
    if root is not None:
        return root
    return Path(os.environ.get("MIND_ROOT") or "mind-root-not-configured")


def _is_safe(target: Path, root: Path) -> bool:
    """Return True if ``target`` lies inside SAFE_PREFIXES.

    Call this BEFORE every real write; reject + ``logger.warning`` otherwise.
    """
    try:
        rel = target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return any(rel == p or rel.startswith(p + "/") for p in SAFE_PREFIXES)


def _kebab(text: str) -> str:
    """Normalise an arbitrary string to kebab-case (Mind convention)."""
    slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", text.strip()).strip("-").lower()
    return re.sub(r"-{2,}", "-", slug)


def _render_digest(messages: List[Dict[str, Any]]) -> str:
    """Render a bounded session digest from the OpenAI-style message list."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: List[str] = [f"# Session Digest — {stamp}", ""]
    count = 0
    for msg in messages or []:
        role = msg.get("role", "")
        content = msg.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        text = content.strip()
        if len(text) > MAX_DIGEST_CHARS_PER_MSG:
            text = text[:MAX_DIGEST_CHARS_PER_MSG].rstrip() + "\n…"
        lines.append(f"## {role}")
        lines.append(text)
        lines.append("")
        count += 1
        if count >= MAX_DIGEST_TURNS:
            lines.append("… (truncated)")
            break
    return "\n".join(lines)


class MindProvider(MemoryProvider):
    """Vaelis memory provider that bridges to the Mind vault."""

    def __init__(self) -> None:
        self._session_id: str = ""
        self._mind_root: Optional[Path] = None
        self._prefetch_cache: Dict[str, str] = {}

    @property
    def name(self) -> str:
        return "mind"

    # -- required abstract methods ---------------------------------------

    def is_available(self) -> bool:
        """Report availability if MIND_ROOT resolves to a real vault."""
        return _resolve_root().is_dir()

    def initialize(self, session_id: str, **kwargs) -> None:
        """Resolve root + session. Builds a writer handle lazily on write."""
        self._session_id = session_id
        self._mind_root = _resolve_root()
        logger.info(
            "[mind] initialized for session %s (root=%s)",
            session_id, self._mind_root,
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """P0: no model-facing tools. P1 will expose mind_read/write/search."""
        return []

    # -- recall (per-turn, injected as context) --------------------------

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant Mind snippets to inject into the system prompt.

        Checks the warm-up cache first (filled by ``queue_prefetch``), then
        falls back to a live keyword search over SAFE_PREFIXES. Returns an
        empty string when nothing relevant is found.
        """
        root = _resolve_root()
        if not root.is_dir() or not query:
            return ""

        cached = self._prefetch_cache.pop(query, None)
        if cached is not None:
            return cached

        try:
            from .retrieval import search as _mind_search

            snippets = _mind_search(root, query, limit=5)
        except Exception as exc:  # noqa: BLE001 - recall must never crash a turn
            logger.warning("[mind] prefetch failed (non-fatal): %s", exc)
            return ""
        return "\n\n".join(snippets)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Queue background recall for the NEXT turn.

        Lightweight synchronous warm-up: runs the keyword search now and
        caches the formatted result so the next ``prefetch(query)`` hits the
        cache instead of scanning the vault again.
        """
        if not query:
            return
        try:
            root = _resolve_root()
            if not root.is_dir():
                return
            from .retrieval import search as _mind_search

            snippets = _mind_search(root, query, limit=5)
            if snippets:
                self._prefetch_cache[query] = "\n\n".join(snippets)
        except Exception as exc:  # noqa: BLE001 - background, never fatal
            logger.warning("[mind] queue_prefetch failed (non-fatal): %s", exc)

    # -- persist (per-turn) ----------------------------------------------

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Write a distilled turn note to Loom/raw/chat-logs/exports/.

        Appends ``<kebab-session>.md`` (one section per turn) via MindWriter.
        Refuses the write unless the resolved path is inside SAFE_PREFIXES.
        """
        try:
            root = _resolve_root()
            if not root.is_dir():
                return
            kebab = _kebab(session_id) or "chat"
            rel = f"Loom/raw/chat-logs/exports/{kebab}.md"
            if not _is_safe((root / rel).resolve(), root):
                logger.warning("[mind] refused sync_turn write: %s", rel)
                return

            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (
                f"## {stamp}\n\n"
                f"### user\n{user_content.strip()}\n\n"
                f"### assistant\n{assistant_content.strip()}\n\n"
            )
            result = MindWriter(root, run_verifier=True, commit=False).write_one(
                rel, body, mode="append"
            )
            if not result.ok:
                logger.warning("[mind] sync_turn write failed: %s", result.detail)
        except Exception as exc:  # noqa: BLE001 - persistence is non-fatal
            logger.warning("[mind] sync_turn failed (non-fatal): %s", exc)

    # -- session boundary ------------------------------------------------

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Digest the session into Loom/raw/chat-logs/digested/<YYYY-MM-DD>/.

        One digest per session (kebab session id, fallback ``session``),
        written via MindWriter after an ``_is_safe`` assertion.
        """
        try:
            root = _resolve_root()
            if not root.is_dir() or not messages:
                return
            today = datetime.now().strftime("%Y-%m-%d")
            kebab = _kebab(self._session_id) or "session"
            rel = f"Loom/raw/chat-logs/digested/{today}/{kebab}-digest.md"
            if not _is_safe((root / rel).resolve(), root):
                logger.warning("[mind] refused on_session_end write: %s", rel)
                return

            result = MindWriter(root, run_verifier=True, commit=False).write_one(
                rel, _render_digest(messages), mode="overwrite"
            )
            if not result.ok:
                logger.warning("[mind] on_session_end write failed: %s", result.detail)
        except Exception as exc:  # noqa: BLE001 - session end must not raise
            logger.warning("[mind] on_session_end failed (non-fatal): %s", exc)

    # -- mirror built-in memory writes -----------------------------------

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror Vaelis MEMORY.md/USER.md writes into the Mind vault.

        - ``remove`` actions never delete from the second brain (log only).
        - concept/entity/source-kind metadata routes to ``Loom/wiki/concepts/``
          (``vaelis-<slug>.md``); everything else lands in
          ``Vault/projects/Vaelis/<slug>.md``.
        - Writes go through MindWriter after an ``_is_safe`` assertion.

        Triggered by MemoryManager.notify_memory_tool_write (verified caller
        at tool_executor.py:1301 / agent_runtime_helpers.py:2298).
        """
        try:
            root = _resolve_root()
            if not root.is_dir():
                return
            if action == "remove":
                logger.info("[mind] on_memory_write 'remove' ignored (never delete from Mind): %s", target)
                return
            if not content:
                return

            slug = _kebab(Path(str(target)).stem) or _kebab(target) or "memory-note"
            meta = metadata or {}
            kind = str(meta.get("kind", "")).lower()
            if kind in ("concept", "entity", "source") or "concepts" in str(target).lower():
                rel = f"Loom/wiki/concepts/vaelis-{slug}.md"
            else:
                rel = f"Vault/projects/Vaelis/{slug}.md"

            if not _is_safe((root / rel).resolve(), root):
                logger.warning("[mind] refused on_memory_write: %s", rel)
                return

            body = f"# {slug}\n\n{content.strip()}\n"
            result = MindWriter(root, run_verifier=True, commit=False).write_one(
                rel, body, mode="overwrite"
            )
            if not result.ok:
                logger.warning("[mind] on_memory_write failed: %s", result.detail)
        except Exception as exc:  # noqa: BLE001 - mirroring is non-fatal
            logger.warning("[mind] on_memory_write failed (non-fatal): %s", exc)

    # -- backup integration ---------------------------------------------

    def backup_paths(self) -> List[str]:
        """Declare Mind root so `hermes backup` includes it (outside HERMES_HOME)."""
        root = _resolve_root()
        return [str(root)] if root.is_dir() else []
