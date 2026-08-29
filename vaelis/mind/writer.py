"""Serialized, model-free writer for the Mind vault.

Why it exists: L2 agents read Mind directly (cheap) but must not write it
concurrently — parallel commits into one git repo trip Mind's verifier. Routing
writes through L1 would serialize them too, but at flagship-model token prices;
this daemon does the same job for the cost of a lock (ADR-0011).

Deliberately dumb: it takes text and a relative path. It never calls a model,
never invents content, and refuses paths outside the tolerated prefixes.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .lock import mind_write_lock
from .paths import MindUnavailable, UnsafeMindPath, require_root, resolve_root, safe_target

logger = logging.getLogger(__name__)

VERIFIER_RELATIVE = "Loom/scripts/verifier.py"


@dataclass
class WriteRequest:
    relative_path: str
    content: str
    # Append is the right default for logs/digests; overwrite for snapshots.
    mode: str = "overwrite"


@dataclass
class WriteResult:
    ok: bool
    written: list[str]
    skipped: list[str]
    detail: str = ""


class MindWriter:
    def __init__(
        self,
        root: Optional[Path | str] = None,
        *,
        commit: bool = False,
        run_verifier: bool = True,
        lock_timeout: float = 30.0,
    ):
        self._explicit_root = root
        self.commit = commit
        self.run_verifier = run_verifier
        self.lock_timeout = lock_timeout

    @property
    def available(self) -> bool:
        return resolve_root(self._explicit_root) is not None

    def _lock_path(self, root: Path) -> Path:
        return root / ".vaelis-mind.lock"

    def write(self, requests: Iterable[WriteRequest]) -> WriteResult:
        """Apply a batch under one lock. Unsafe paths are skipped, not fatal."""
        batch = list(requests)
        if not batch:
            return WriteResult(ok=True, written=[], skipped=[])

        try:
            root = require_root(self._explicit_root)
        except MindUnavailable as exc:
            return WriteResult(ok=False, written=[], skipped=[r.relative_path for r in batch], detail=str(exc))

        written: list[str] = []
        skipped: list[str] = []

        with mind_write_lock(self._lock_path(root), timeout=self.lock_timeout):
            for request in batch:
                try:
                    target = safe_target(root, request.relative_path)
                except UnsafeMindPath as exc:
                    logger.warning("mind: refused write to %s (%s)", request.relative_path, exc)
                    skipped.append(request.relative_path)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                if request.mode == "append" and target.exists():
                    with open(target, "a", encoding="utf-8") as handle:
                        handle.write(request.content)
                else:
                    target.write_text(request.content, encoding="utf-8")
                written.append(request.relative_path)

            if not written:
                return WriteResult(ok=False, written=[], skipped=skipped, detail="nothing written")

            if self.run_verifier:
                ok, detail = self._verify(root)
                if not ok:
                    # Files stay on disk (Mind is a working copy, not a
                    # transaction); we just refuse to commit a tree the
                    # verifier rejects and surface why.
                    return WriteResult(ok=False, written=written, skipped=skipped, detail=detail)

            if self.commit:
                ok, detail = self._commit(root, written)
                return WriteResult(ok=ok, written=written, skipped=skipped, detail=detail)

        return WriteResult(ok=True, written=written, skipped=skipped)

    def write_one(self, relative_path: str, content: str, *, mode: str = "overwrite") -> WriteResult:
        return self.write([WriteRequest(relative_path=relative_path, content=content, mode=mode)])

    # --- guards -------------------------------------------------------------

    def _verify(self, root: Path) -> tuple[bool, str]:
        script = root / VERIFIER_RELATIVE
        if not script.is_file():
            return True, "verifier not present"

        import sys

        try:
            completed = subprocess.run(
                [sys.executable, str(script), "--strict"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # A broken verifier must not block the secretary; log and continue.
            logger.warning("mind: verifier could not run: %s", exc)
            return True, f"verifier skipped: {exc}"

        if completed.returncode != 0:
            tail = (completed.stdout or completed.stderr or "").strip()[-400:]
            return False, f"verifier blocked the write: {tail}"
        return True, "verifier clean"

    def _commit(self, root: Path, paths: list[str]) -> tuple[bool, str]:
        try:
            subprocess.run(["git", "add", *paths], cwd=str(root), check=True, capture_output=True, timeout=60)
            completed = subprocess.run(
                ["git", "commit", "-m", f"chore(vaelis): update {len(paths)} file(s)"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"git commit failed: {exc}"

        if completed.returncode != 0:
            output = (completed.stdout or "") + (completed.stderr or "")
            if "nothing to commit" in output:
                return True, "nothing to commit"
            return False, output.strip()[-400:]
        return True, "committed"


_DEFAULT: Optional[MindWriter] = None


def get_writer() -> MindWriter:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = MindWriter()
    return _DEFAULT


def set_writer(writer: Optional[MindWriter]) -> None:
    global _DEFAULT
    _DEFAULT = writer
