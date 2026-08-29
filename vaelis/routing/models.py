"""Role → model routing.

Turns the cost discipline in docs/adr/0011-three-tier-agents-and-model-routing.md
into something the code can enforce:

- **L1** runs the best available model (currently Kimi K3) and only ever
  statuses, decides, delegates. It must never be pointed at a free-tier GUI
  surface, and never at the same model as L2 (that would mean the expensive
  model is doing clerical work).
- **L2** runs cheap models or aggregated quota and does the per-message
  classification, extraction and tool loops.
- **L3** spends no tokens at all — it drives GUIs.

Config: ``$HERMES_HOME/vaelis/models.json`` (ids only; API keys stay in env,
per AGENTS.md).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

L1_SECRETARY = "l1_secretary"
L2_AGENDA = "l2_agenda"
L2_PLANNER = "l2_planner"
L2_PROJECT = "l2_project"

KNOWN_ROLES = (L1_SECRETARY, L2_AGENDA, L2_PLANNER, L2_PROJECT)

# Surfaces whose quota cannot be converted into an API key. They belong to L3
# workers; wiring one to L1 would make the secretary depend on GUI automation.
GUI_ONLY_SURFACES = ("marvis", "cursor", "antigravity-gui", "workbuddy", "gui")

DEFAULT_ROUTES: dict[str, dict[str, str]] = {
    L1_SECRETARY: {"provider": "moonshot", "model": "kimi-k3"},
    L2_AGENDA: {"provider": "deepseek", "model": "deepseek-chat"},
    L2_PLANNER: {"provider": "deepseek", "model": "deepseek-chat"},
    L2_PROJECT: {"provider": "deepseek", "model": "deepseek-chat"},
}


class RoutingError(ValueError):
    pass


def config_path() -> Path:
    override = os.environ.get("VAELIS_MODELS_CONFIG", "").strip()
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        root = get_hermes_home() / "vaelis"
    except Exception:
        root = Path.home() / ".hermes" / "vaelis"
    return root / "models.json"


@dataclass(frozen=True)
class ModelRoute:
    role: str
    provider: str = ""
    model: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.model)

    @property
    def qualified(self) -> str:
        if self.provider and self.model:
            return f"{self.provider}/{self.model}"
        return self.model or self.provider

    @property
    def is_gui_surface(self) -> bool:
        blob = f"{self.provider} {self.model}".lower()
        return any(surface in blob for surface in GUI_ONLY_SURFACES)


@dataclass
class ModelRouter:
    routes: dict[str, ModelRoute] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "ModelRouter":
        target = Path(path) if path else config_path()
        raw: dict = {}
        if target.exists():
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded.get("roles") if isinstance(loaded.get("roles"), dict) else loaded
            except (OSError, json.JSONDecodeError):
                logger.warning("vaelis: could not read %s; using defaults", target)

        routes: dict[str, ModelRoute] = {}
        for role, defaults in DEFAULT_ROUTES.items():
            entry = raw.get(role) if isinstance(raw.get(role), dict) else {}
            routes[role] = ModelRoute(
                role=role,
                provider=str(entry.get("provider") or defaults["provider"]),
                model=str(entry.get("model") or defaults["model"]),
            )

        # Roles the operator invented (extra project agents) are kept as-is.
        for role, entry in raw.items():
            if role in routes or not isinstance(entry, dict):
                continue
            routes[role] = ModelRoute(
                role=role,
                provider=str(entry.get("provider") or ""),
                model=str(entry.get("model") or ""),
            )

        return cls(routes=routes)

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path else config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "roles": {
                        role: {"provider": route.provider, "model": route.model}
                        for role, route in sorted(self.routes.items())
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    def resolve(self, role: str) -> ModelRoute:
        route = self.routes.get(role)
        if route is None:
            raise RoutingError(f"no model route configured for role {role!r}")
        return route

    def is_l1(self, role: str) -> bool:
        return role == L1_SECRETARY

    def violations(self) -> list[str]:
        """Contract checks. Empty list means the routing obeys ADR-0011."""
        problems: list[str] = []

        l1 = self.routes.get(L1_SECRETARY)
        if l1 is None or not l1.configured:
            problems.append("l1_secretary has no model configured")
            return problems

        if l1.is_gui_surface:
            problems.append(
                f"l1_secretary points at a GUI-only surface ({l1.qualified}); "
                "those belong to L3 workers"
            )

        for role, route in self.routes.items():
            if role == L1_SECRETARY:
                continue
            if not route.configured:
                problems.append(f"{role} has no model configured")
                continue
            if route.qualified == l1.qualified:
                problems.append(
                    f"{role} shares L1's model ({route.qualified}); the expensive "
                    "model would end up doing per-message work"
                )

        return problems

    def assert_valid(self) -> None:
        problems = self.violations()
        if problems:
            raise RoutingError("; ".join(problems))


_DEFAULT: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ModelRouter.load()
        for problem in _DEFAULT.violations():
            logger.warning("vaelis model routing: %s", problem)
    return _DEFAULT


def set_router(router: Optional[ModelRouter]) -> None:
    global _DEFAULT
    _DEFAULT = router
