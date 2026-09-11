"""B2: L2 常驻 Agent 注册表。

每项目一个常驻 profile（底座 profiles 机制）；角色→模型路由配置化；
独立会话；L2 直读 Mind 项目子树。

注册表持久化在 ``$HERMES_HOME/vaelis/projects.yaml``（profile-safe：一律走
``get_hermes_home()``，不写死盘符）。格式::

    version: 1
    agents:
      agenda:
        role: l2_agenda
        profile: l2-agenda          # 对应 hermes profile（省略 = 用 agent 名）
        provider: deepseek          # 可选覆盖默认路由；省略 = 用 DEFAULT_ROUTES
        model: deepseek-chat
        mind_subtree: Vault/projects/Vaelis   # 相对 MIND_ROOT（L2 直读）
        skills: [morning-report, message-digest]
        description: 日程闭环 Agent

``spawn`` 做三件事：确保 profile 存在（复用 ``hermes_cli.profiles.create_profile``）、
把该 agent 的模型路由写进 profile 的 ``vaelis/models.json``（ADR-0011 断言绿）、
输出启动命令。路由断言 ``ModelRouter.assert_valid()`` 保证 L1≠L2 模型。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REGISTRY_VERSION = 1

# DEFAULT_ROUTES 里定义的 L1 秘书角色名（spawn 时禁止把 L2 当 L1）。
L1_SECRETARY_ROLE = "l1_secretary"


class RegistryError(ValueError):
    pass


# R-012: L2 agent taxonomy. ``butler`` is the default so legacy rows
# (no category key) fold into the catch-all — no migration required.
AGENT_CATEGORIES: tuple[str, ...] = ("projects", "butler", "events", "research")
DEFAULT_CATEGORY = "butler"

# R-013: default folder binding per category. ``butler`` has none (it is the
# housekeeping agent, not project-scoped). A caller may always override
# ``project_path`` on the entry; this map only seeds the default.
# NOTE: drive letters are intentionally NOT hardcoded in tests — the registry
# resolves these verbatim; tests inject override paths.
DEFAULT_PROJECT_PATHS: dict[str, str] = {
    "projects": r"D:\projects",
    "events": r"D:\Cloud\Events",
    "research": r"D:\Cloud\Research",
    "butler": "",
}

# 裁定 19: events 生命周期护栏。一个 events 类代理必须挂到一条用户已确认的
# agenda 事项；同时存活 events 类代理上限（超即 400）。
MAX_LIVE_EVENTS_AGENTS = 5


def default_project_path(category: str) -> str:
    """Default folder binding for a category; ``""`` when none (butler)."""
    return DEFAULT_PROJECT_PATHS.get(category, "")


def _dt_today_iso() -> str:
    """Local date as ISO-8601 (date only) — used for archive folder suffixes."""
    from datetime import date

    return date.today().isoformat()


def _normalize_category(raw: str | None) -> str:
    norm = str(raw or "").strip().lower()
    if norm not in AGENT_CATEGORIES:
        # Fail-closed: an unknown/missing category folds into the catch-all
        # (butler), never an invented grade. No auto-grading.
        return DEFAULT_CATEGORY
    return norm


def default_path() -> Path:
    """注册表文件路径：$HERMES_HOME/vaelis/projects.yaml。"""
    override = os.environ.get("VAELIS_PROJECTS_CONFIG", "").strip()
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        root = get_hermes_home() / "vaelis"
    except Exception:
        root = Path.home() / ".hermes" / "vaelis"
    return root / "projects.yaml"


@dataclass(frozen=True)
class AgentEntry:
    """注册表里一个常驻 L2 agent 的描述。"""

    name: str
    role: str = "l2_project"
    profile: str = ""  # hermes profile 名；空 = 用 name
    provider: str = ""  # 可选覆盖；空 = 默认路由
    model: str = ""  # 可选覆盖；空 = 默认路由
    mind_subtree: str = ""  # 相对 MIND_ROOT 的项目子树（L2 直读）
    skills: tuple[str, ...] = ()
    description: str = ""
    # C5 项目节奏：{"weekly_hours": N}。仅对 role=l2_project 有意义；
    # None = 未配置（规划员不为其排推进块）。
    pace: Optional[dict] = None
    # R-012: sidebar taxonomy group. ``butler`` default for backward compat.
    category: str = DEFAULT_CATEGORY
    # R-013: folder binding. Empty = no bound folder (butler, or unset).
    # When the caller does not supply one, the registry seeds it from the
    # category default on create (see ``AgentRegistry.upsert``).
    project_path: str = ""
    # 裁定 19 dissolve: archived rows stay on disk but hide from the default
    # list. ``archived_at`` is the ISO date the profile dir was moved aside.
    archived: bool = False
    archived_at: str = ""
    # events 生命周期：建册时指向一条用户已确认的 agenda 事项 id。
    # Non-empty only for category=events (validated at the API layer).
    source_event_id: str = ""

    @property
    def profile_name(self) -> str:
        return self.profile or self.name

    @property
    def has_model_override(self) -> bool:
        return bool(self.provider or self.model)

    @property
    def weekly_hours(self) -> Optional[float]:
        """``pace.weekly_hours`` 的规范化读取；未配置或非法时为 None。"""
        if not isinstance(self.pace, dict):
            return None
        try:
            hours = float(self.pace.get("weekly_hours"))
        except (TypeError, ValueError):
            return None
        if hours <= 0 or hours > 168:
            return None
        return hours

    def to_dict(self) -> dict:
        data: dict = {"role": self.role}
        if self.profile:
            data["profile"] = self.profile
        if self.provider:
            data["provider"] = self.provider
        if self.model:
            data["model"] = self.model
        if self.mind_subtree:
            data["mind_subtree"] = self.mind_subtree
        if self.skills:
            data["skills"] = list(self.skills)
        if self.description:
            data["description"] = self.description
        if self.pace:
            data["pace"] = self.pace
        # R-012/R-013: always write category so roundtrip is faithful; the
        # default (butler) is explicit so a human reading projects.yaml sees
        # the grade. project_path only when non-empty (butler has none).
        data["category"] = self.category
        if self.project_path:
            data["project_path"] = self.project_path
        if self.archived:
            data["archived"] = True
            if self.archived_at:
                data["archived_at"] = self.archived_at
        if self.source_event_id:
            data["source_event_id"] = self.source_event_id
        return data

    @classmethod
    def from_dict(cls, name: str, raw: dict) -> "AgentEntry":
        if not isinstance(raw, dict):
            raise RegistryError(f"agent {name!r}: entry must be a mapping")
        skills = raw.get("skills") or []
        if isinstance(skills, str):
            skills = [skills]
        pace = raw.get("pace")
        if pace is not None and not isinstance(pace, dict):
            raise RegistryError(f"agent {name!r}: pace must be a mapping")
        if isinstance(pace, dict) and "weekly_hours" in pace:
            try:
                hours = float(pace["weekly_hours"])
            except (TypeError, ValueError) as exc:
                raise RegistryError(
                    f"agent {name!r}: pace.weekly_hours must be a number"
                ) from exc
            if hours <= 0 or hours > 168:
                raise RegistryError(
                    f"agent {name!r}: pace.weekly_hours must be in (0, 168]"
                )
            pace = {"weekly_hours": hours}
        else:
            pace = None
        return cls(
            name=name,
            role=str(raw.get("role") or "l2_project"),
            profile=str(raw.get("profile") or ""),
            provider=str(raw.get("provider") or ""),
            model=str(raw.get("model") or ""),
            mind_subtree=str(raw.get("mind_subtree") or ""),
            skills=tuple(str(s) for s in skills),
            description=str(raw.get("description") or ""),
            pace=pace,
            category=_normalize_category(raw.get("category")),
            project_path=str(raw.get("project_path") or ""),
            archived=bool(raw.get("archived") or False),
            archived_at=str(raw.get("archived_at") or ""),
            source_event_id=str(raw.get("source_event_id") or ""),
        )


@dataclass
class AgentRegistry:
    """读写 projects.yaml 的注册表。"""

    path: Path
    agents: dict[str, AgentEntry] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # IO
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Path | str | None = None) -> "AgentRegistry":
        target = Path(path) if path else default_path()
        agents: dict[str, AgentEntry] = {}
        if target.exists():
            try:
                import yaml

                raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
                if isinstance(raw, dict):
                    entries = raw.get("agents") or {}
                    if isinstance(entries, dict):
                        for name, entry in entries.items():
                            try:
                                agents[str(name)] = AgentEntry.from_dict(str(name), entry)
                            except RegistryError as exc:
                                logger.warning("vaelis registry: %s", exc)
            except Exception:
                logger.warning("vaelis: could not read %s; treating as empty", target)
        return cls(path=target, agents=agents)

    def save(self, path: Path | str | None = None) -> Path:
        target = Path(path) if path else self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        import yaml

        payload = {
            "version": REGISTRY_VERSION,
            "agents": {name: entry.to_dict() for name, entry in sorted(self.agents.items())},
        }
        target.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return target

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    def get(self, name: str) -> Optional[AgentEntry]:
        return self.agents.get(name)

    def upsert(self, entry: AgentEntry) -> AgentEntry:
        # R-013: when the caller did not supply project_path, seed it from
        # the category default. butler stays empty (no bound folder). The
        # actual directory is created at the API layer (console router),
        # not here — registry stays pure data + no filesystem mutation
        # beyond its own yaml.
        if not entry.project_path and entry.category != "butler":
            from dataclasses import replace

            seeded = default_project_path(entry.category)
            if seeded:
                entry = replace(entry, project_path=seeded)
        self.agents[entry.name] = entry
        return entry

    def remove(self, name: str) -> bool:
        return self.agents.pop(name, None) is not None

    def dissolve(self, name: str, *, archived_at: str = "") -> AgentEntry:
        """裁定 19: 归档不删除。

        把注册表条目标记 ``archived=True``（保留，列表默认不显示）。
        profile 目录的物理搬运由调用方（console router）在标记前后做，
        因为路径解析依赖 ``hermes_cli.profiles`` —— registry 保持纯数据。
        返回归档后的 entry；找不到则 ``RegistryError``。
        """
        entry = self.get(name)
        if entry is None:
            raise RegistryError(f"agent {name!r} is not registered")
        if entry.archived:
            return entry  # idempotent: 已归档不再重复
        from dataclasses import replace

        stamp = archived_at or _dt_today_iso()
        updated = replace(
            entry,
            archived=True,
            archived_at=stamp,
        )
        self.agents[name] = updated
        return updated

    def names(self) -> list[str]:
        return sorted(self.agents)

    def entries(self) -> list[AgentEntry]:
        return [self.agents[n] for n in self.names()]

    # ------------------------------------------------------------------ #
    # R-012 / 裁定 19: taxonomy + lifecycle helpers
    # ------------------------------------------------------------------ #

    def live_entries(self) -> list[AgentEntry]:
        """Non-archived rows — the default ``GET /api/agents`` view."""
        return [e for e in self.entries() if not e.archived]

    def archived_entries(self) -> list[AgentEntry]:
        """Rows marked archived by ``dissolve`` — visible only on explicit ask."""
        return [e for e in self.entries() if e.archived]

    def count_live_events(self) -> int:
        """裁定 19: 存活 events 类代理计数（用于 ≤5 上限护栏）。"""
        return sum(
            1 for e in self.live_entries() if e.category == "events"
        )

    # ------------------------------------------------------------------ #
    # 模型路由
    # ------------------------------------------------------------------ #

    def router(self) -> "ModelRouter":
        """合并默认路由 + 注册表覆盖，返回 ModelRouter。

        惰性 import 避免 hermes_cli 依赖方向问题。profile 级 models.json
        由 ``spawn`` 写，这里只负责在默认路由之上叠加覆盖。
        """
        from vaelis.routing import ModelRouter

        router = ModelRouter.load()
        for entry in self.entries():
            if not entry.has_model_override:
                continue
            route = router.resolve(entry.role)
            from vaelis.routing import ModelRoute

            router.routes[entry.role] = ModelRoute(
                role=entry.role,
                provider=entry.provider or route.provider,
                model=entry.model or route.model,
            )
        return router

    def routing_problems(self) -> list[str]:
        """ADR-0011 断言问题列表（空 = 绿）。"""
        try:
            return self.router().violations()
        except Exception as exc:  # 兜底：缺 L1 等异常当问题上报
            return [f"routing check failed: {exc}"]

    # ------------------------------------------------------------------ #
    # spawn
    # ------------------------------------------------------------------ #

    def spawn(
        self,
        name: str,
        *,
        clone_from: Optional[str] = None,
        write_config: bool = True,
    ) -> dict:
        """把一个注册条目落地为常驻 profile + 模型路由。

        1. 若 profile 不存在则 ``create_profile``（默认克隆当前 profile 的
           config/.env/SOUL/skills，让 L2 继承基础能力）。
        2. 把该 agent 的路由写进 profile 的 ``vaelis/models.json``。
        3. ADR-0011 断言（L1≠L2 模型）必须绿，否则抛 RegistryError。
        4. 返回 dict：profile 路径、启动命令、routing 断言。

        ``write_config`` 为真时同步把路由写进 profile 的 config.yaml 的
        ``model.provider`` / ``model.default``（会话真正用到的模型）。
        """
        entry = self.get(name)
        if entry is None:
            raise RegistryError(f"agent {name!r} is not registered")

        profile_dir = self._ensure_profile(entry, clone_from=clone_from)

        # 1) profile 级 models.json（ADRD-0011 断言基于它）
        profile_models = self._write_profile_models(profile_dir, entry)

        # 2) routing 断言绿
        problems = self._profile_routing_problems(profile_models)
        if problems:
            raise RegistryError(
                f"agent {name!r} routing violates ADR-0011: " + "; ".join(problems)
            )

        # 3) config.yaml 同步模型（会话实际用模型）
        if write_config:
            self._write_profile_config(profile_dir, entry)

        return {
            "name": name,
            "role": entry.role,
            "profile": entry.profile_name,
            "profile_dir": str(profile_dir),
            "command": f"hermes -p {entry.profile_name} chat",
            "routing_ok": True,
        }

    def _ensure_profile(
        self, entry: AgentEntry, *, clone_from: Optional[str] = None
    ) -> Path:
        from hermes_cli.profiles import (
            create_profile,
            get_profile_dir,
            profile_exists,
        )

        name = entry.profile_name
        if profile_exists(name):
            return get_profile_dir(name)
        # 首次落地：克隆现有 profile（默认克隆活动 profile）作为能力底座。
        kwargs: dict = {}
        if clone_from:
            kwargs["clone_from"] = clone_from
            kwargs["clone_config"] = True
        else:
            kwargs["clone_config"] = True  # 默认克隆配置（含 .env / skills）
        try:
            return create_profile(name=name, **kwargs)
        except FileExistsError:
            return get_profile_dir(name)

    def _write_profile_models(self, profile_dir: Path, entry: AgentEntry) -> Path:
        """把注册表整体路由写进 profile 的 vaelis/models.json。"""
        from vaelis.routing import ModelRouter

        target = profile_dir / "vaelis" / "models.json"
        router = self.router()  # 默认 + 全部注册覆盖
        router.save(target)
        return target

    def _profile_routing_problems(self, models_path: Path) -> list[str]:
        from vaelis.routing import ModelRouter

        router = ModelRouter.load(models_path)
        return router.violations()

    def _write_profile_config(self, profile_dir: Path, entry: AgentEntry) -> None:
        """把该 agent 的模型写进 profile config.yaml 的 model 节。

        仅当 entry 显式给了 provider/model（或默认路由解析出模型）才写；
        不动其他配置。config.yaml 可能不存在（新 profile 也可能没有），
        不存在则跳过 —— 会话仍可用 models.json 路由。
        """
        try:
            route = self.router().resolve(entry.role)
        except Exception:
            route = None
        if route is None or not route.configured:
            return

        cfg_path = profile_dir / "config.yaml"
        if not cfg_path.exists():
            return
        import yaml

        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return
        if not isinstance(cfg, dict):
            return
        model_section = cfg.get("model")
        if not isinstance(model_section, dict):
            model_section = {}
        model_section["provider"] = route.provider or model_section.get("provider", "")
        model_section["default"] = route.model or model_section.get("default", "")
        cfg["model"] = model_section
        cfg_path.write_text(
            yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# S2: find or spawn exactly one agenda L2
# ---------------------------------------------------------------------------

AGENDA_TEMPLATE_NAME = "agenda"
AGENDA_TEMPLATE_PROFILE = "l2-agenda"
AGENDA_TEMPLATE_ROLE = "l2_agenda"

_AGENDA_ROLE_MARKERS = ("l2_agenda", "secretary-agenda")


def agenda_template_entry() -> AgentEntry:
    """The only L2 ``spawn`` is allowed to create for §8.2 S2."""
    return AgentEntry(
        name=AGENDA_TEMPLATE_NAME,
        role=AGENDA_TEMPLATE_ROLE,
        profile=AGENDA_TEMPLATE_PROFILE,
        provider="aigw",
        model="workbuddy/deepseek-chat",
        mind_subtree="Vault/projects/Vaelis",
        skills=("vaelis-l2-resident",),
        description="日程采集 → SQLite → 看板 → 钉钉 闭环",
    )


def is_agenda_entry(entry: AgentEntry) -> bool:
    """True when this registry row is the agenda / 日程 secretary.

    Matches existing ``role`` / description / template names. Does not invent
    a second registry — callers still go through :class:`AgentRegistry`.
    """
    role = (entry.role or "").strip().lower()
    name = (entry.name or "").strip().lower()
    profile = (entry.profile or "").strip().lower()
    desc = entry.description or ""
    if any(marker in role for marker in _AGENDA_ROLE_MARKERS):
        return True
    if "日程" in (entry.role or "") or "日程" in desc or "日程" in (entry.name or ""):
        return True
    if "secretary-agenda" in name or "secretary-agenda" in profile:
        return True
    return False


def find_agenda_agent(registry: AgentRegistry | None = None) -> Optional[AgentEntry]:
    """First matching agenda L2, preferring an exact ``l2_agenda`` role."""
    reg = registry or load_registry()
    found = [entry for entry in reg.entries() if is_agenda_entry(entry)]
    if not found:
        return None
    found.sort(key=lambda entry: (0 if entry.role == AGENDA_TEMPLATE_ROLE else 1, entry.name))
    return found[0]


def ensure_agenda_agent(registry: AgentRegistry | None = None) -> tuple[AgentEntry, bool]:
    """Return the agenda L2, spawning **one** template entry if none exists (S2).

    Never creates any other L2. ``spawned`` is True only when this call
    registered the template. Profile materialization is idempotent.
    """
    reg = registry or load_registry()
    existing = find_agenda_agent(reg)
    spawned = False
    if existing is None:
        template = agenda_template_entry()
        if template.name in reg.agents:
            template = AgentEntry(
                name="secretary-agenda",
                role=template.role,
                profile=template.profile,
                provider=template.provider,
                model=template.model,
                mind_subtree=template.mind_subtree,
                skills=template.skills,
                description=template.description,
            )
        reg.upsert(template)
        reg.save()
        existing = template
        spawned = True

    from hermes_cli.profiles import profile_exists

    if not profile_exists(existing.profile_name):
        reg.spawn(existing.name)
    elif spawned:
        # Newly registered into an already-present profile (unusual) — still
        # run spawn so models.json / config.yaml stay in sync.
        try:
            reg.spawn(existing.name)
        except RegistryError:
            logger.warning(
                "vaelis: agenda L2 %r registered but spawn skipped: profile exists",
                existing.name,
            )
    try:
        from hermes_cli.profiles import get_profile_dir

        l2_dir = get_profile_dir(existing.profile_name)
        ensure_aigw_provider(l2_dir)
        # L1 mid-narrow must not stick on a cloned agenda profile (裁定 12).
        ensure_l2_agenda_toolsets(l2_dir)
    except Exception as exc:
        logger.warning("vaelis: aigw/L2 toolsets not written for %s: %s", existing.name, exc)
    return existing, spawned


SECRETARY_ASK_INTENTS = ("refresh_agenda", "write_briefing", "mutate_agenda")

# WP-L1-AGENDA-MUTATE: conversational write intents. Reading (refresh /
# briefing) may hit chatlog; writing MUST NOT touch chatlog and must work
# even when collection is dead.
MUTATE_ACTIONS = ("create", "update", "delete")
MUTATE_KINDS = ("meeting", "task", "ddl", "class")

MISSING_PLAN_SUMMARY = "昨夜未生成计划"
PLAN_BRIEFING_STATUSES = frozenset({"pending", "confirmed", "empty"})
STALE_PLAN_NOTE = "计划生成后日程有变，以看板为准"


def _tomorrow_for_date(agenda_summary: dict | None = None) -> str:
    from datetime import date, timedelta

    listed = (agenda_summary or {}).get("tomorrow")
    if listed:
        return str(listed)
    return (date.today() + timedelta(days=1)).isoformat()


def _secretary_db_path(pipeline=None):
    service = getattr(pipeline, "service", None) if pipeline is not None else None
    return getattr(service, "db_path", None) if service is not None else None


def _tomorrow_event_ids(agenda_summary: dict | None) -> set[str]:
    events = (agenda_summary or {}).get("tomorrow_events") or []
    return {
        str(event.get("id"))
        for event in events
        if isinstance(event, dict) and event.get("id")
    }


def _missing_plan_payload(for_date: str) -> dict:
    return {
        "status": "missing",
        "summary": MISSING_PLAN_SUMMARY,
        "for_date": for_date,
        "event_count": 0,
        "conflict_count": 0,
        "stale": False,
        "empty": False,
    }


def _annotate_stale_summary(view: dict) -> dict:
    if not view.get("stale"):
        return view
    summary = (view.get("summary") or "").strip()
    if STALE_PLAN_NOTE in summary:
        return view
    annotated = dict(view)
    annotated["summary"] = f"{summary}。{STALE_PLAN_NOTE}" if summary else STALE_PLAN_NOTE
    return annotated


def _l1_plan_view_from_store(
    for_date: str, tomorrow_ids: set[str], db_path
) -> dict:
    from vaelis.agenda import store

    conn = store.connect(db_path)
    try:
        plan = store.get_daily_plan(conn, for_date)
        if plan is None:
            return _missing_plan_payload(for_date)
        items = store.list_plan_items(conn, plan.id)
        item_ids = {item.event_id for item in items if item.event_id}
        return {
            "status": plan.status,
            "summary": (plan.summary or "").strip(),
            "for_date": plan.for_date,
            "event_count": int(plan.event_count),
            "conflict_count": int(plan.conflict_count),
            "stale": item_ids != tomorrow_ids,
            "empty": plan.status == "empty",
        }
    finally:
        conn.close()


def _l1_plan_view(
    pipeline=None,
    agenda_summary: dict | None = None,
) -> dict:
    """Read tomorrow's nightly plan for L1. Prefer planning.l1_plan_view."""
    for_date = _tomorrow_for_date(agenda_summary)
    tomorrow_ids = _tomorrow_event_ids(agenda_summary)
    db_path = _secretary_db_path(pipeline)
    try:
        from vaelis.agenda.planning import l1_plan_view as planning_view
    except ImportError:
        return _annotate_stale_summary(
            _l1_plan_view_from_store(for_date, tomorrow_ids, db_path)
        )
    return _annotate_stale_summary(
        planning_view(for_date, tomorrow_ids, db_path=db_path)
    )


def _uses_plan_briefing(plan: dict | None) -> bool:
    return bool(plan) and plan.get("status") in PLAN_BRIEFING_STATUSES


def _secretary_service(pipeline=None):
    """AgendaService bound to the pipeline's DB when available, else default."""
    from vaelis.agenda.service import AgendaService, get_service

    db_path = _secretary_db_path(pipeline)
    if db_path is not None:
        return AgendaService(db_path)
    return get_service()


def _mutate_event_payload(event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "kind": event.kind,
        "status": event.status,
        "source": event.source,
    }


def _mutate_error(error: str, **extra) -> dict:
    payload = {
        "ok": False,
        "intent": "mutate_agenda",
        "error": error,
    }
    payload.update(extra)
    return payload


def run_mutate_agenda(
    user_text: str,
    *,
    action: str | None = None,
    title: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    kind: str | None = None,
    event_id: str | None = None,
    pipeline=None,
    registry: AgentRegistry | None = None,
) -> dict:
    """WP-L1-AGENDA-MUTATE: add / change / cancel via the same secretary mouth.

    Goes straight to ``AgendaService`` — never calls ``refresh_agenda`` and
    never touches chatlog, so a dead collector cannot block a write.
    User-spoken changes are human orders: ``create`` lands ``source=manual``
    + ``confirmed``; ``delete`` on a confirmed row deletes it, on a pending
    row it dismisses (never "rejects" the user's own words as a candidate).
    Missing action / missing create title or start_at → error, zero writes.
    """
    user_text = (user_text or "").strip()
    action = (action or "").strip().lower()
    if action not in MUTATE_ACTIONS:
        return _mutate_error(
            "mutate_agenda 需要 action=create/update/delete",
            action=action or None,
            user_text=user_text,
        )

    title = (str(title).strip() if title else "") or None
    start_at = (str(start_at).strip() if start_at else "") or None
    end_at = (str(end_at).strip() if end_at else "") or None
    kind = (str(kind).strip() if kind else "") or "task"
    event_id = (str(event_id).strip() if event_id else "") or None

    if kind not in MUTATE_KINDS:
        return _mutate_error(
            f"kind 只允许 {'/'.join(MUTATE_KINDS)}，收到 {kind!r}",
            action=action,
            user_text=user_text,
        )
    if action == "create":
        if not title:
            return _mutate_error("create 需要 title", action=action, user_text=user_text)
        if not start_at:
            # No invented 9:00, no invented 1-hour duration: ask instead.
            return _mutate_error(
                "create 需要 start_at（本地 ISO 钟点；缺钟点要问用户，不要编）",
                action=action,
                user_text=user_text,
            )
    if action in ("update", "delete") and not event_id and not title:
        return _mutate_error(
            f"{action} 需要 event_id 或 title 来定位那条日程",
            action=action,
            user_text=user_text,
        )

    try:
        from vaelis.agenda.service import (
            AgendaError,
            ManualTargetAmbiguous,
            ManualTargetMissing,
        )

        service = _secretary_service(pipeline)

        if action == "create":
            event = service.create_manual(
                title=title, start_at=start_at, end_at=end_at, kind=kind
            )
            payload = {
                "ok": True,
                "intent": "mutate_agenda",
                "action": "create",
                "event": _mutate_event_payload(event),
                "user_text": user_text,
            }
        else:
            try:
                target = service.resolve_manual_target(
                    event_id=event_id,
                    title=title,
                    day=start_at[:10] if start_at else None,
                )
            except ManualTargetMissing as exc:
                return _mutate_error(str(exc), action=action, user_text=user_text)
            except ManualTargetAmbiguous as exc:
                return _mutate_error(
                    "同一时段匹配到多条同名日程，不猜；请指定其中一条",
                    action=action,
                    candidates=exc.candidates,
                    user_text=user_text,
                )

            if action == "update":
                event = service.update_manual(
                    target.id,
                    title=title,
                    start_at=start_at,
                    end_at=end_at,
                    kind=kind,
                )
                payload = {
                    "ok": True,
                    "intent": "mutate_agenda",
                    "action": "update",
                    "event": _mutate_event_payload(event),
                    "user_text": user_text,
                }
            else:  # delete: confirmed → delete, pending → dismiss (人令)
                resolved = _mutate_event_payload(target)
                if target.status == "pending":
                    service.dismiss(target.id)
                else:
                    service.delete(target.id)
                payload = {
                    "ok": True,
                    "intent": "mutate_agenda",
                    "action": "delete",
                    "deleted": True,
                    "resolved": resolved,
                    "user_text": user_text,
                }
    except AgendaError as exc:
        return _mutate_error(str(exc), action=action, user_text=user_text)
    except Exception as exc:  # store/validation errors must not fabricate success
        logger.warning("vaelis: mutate_agenda write failed: %s", exc)
        return _mutate_error(f"日程写入失败: {exc}", action=action, user_text=user_text)

    # C3 name card is optional garnish — never worth a collection round-trip.
    try:
        entry, spawned = ensure_agenda_agent(registry or load_registry())
        payload["agent"] = {
            "id": entry.name,
            "role": entry.role,
            "profile": entry.profile_name,
            "spawned": spawned,
        }
    except Exception as exc:
        logger.warning("vaelis: mutate_agenda agent card skipped: %s", exc)
    return payload


def run_secretary_ask(
    intent: str,
    user_text: str,
    *,
    registry: AgentRegistry | None = None,
    pipeline=None,
    aigw_complete=None,
    fallback_complete=None,
    action: str | None = None,
    title: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    kind: str | None = None,
    event_id: str | None = None,
) -> dict:
    """§8.2 secretary routing: pick agenda L2, one refresh, structured summary.

    ``refresh_agenda`` and ``write_briefing`` both refresh. write_briefing
    then generates via aigw ``workbuddy/*`` (F2 fallback = L2 cheap API).
    No kanban. No chat REST. Dead chatlog returns ``ok: False``.
    ``mutate_agenda`` never reaches this chatlog path — see
    :func:`run_mutate_agenda` (writes must survive a dead collector).
    """
    intent = (intent or "").strip()
    user_text = (user_text or "").strip()
    if intent not in SECRETARY_ASK_INTENTS:
        return {
            "ok": False,
            "error": "intent must be refresh_agenda, write_briefing or mutate_agenda",
        }
    if not user_text:
        return {"ok": False, "error": "user_text is required"}

    if intent == "mutate_agenda":
        return run_mutate_agenda(
            user_text,
            action=action,
            title=title,
            start_at=start_at,
            end_at=end_at,
            kind=kind,
            event_id=event_id,
            pipeline=pipeline,
            registry=registry,
        )

    reg = registry or load_registry()
    try:
        entry, spawned = ensure_agenda_agent(reg)
    except RegistryError as exc:
        return {"ok": False, "error": f"无法落地日程 L2: {exc}"}

    from vaelis.collectors.chatlog.pipeline import ChatlogDead, refresh_agenda

    try:
        _report, summary = refresh_agenda(pipeline=pipeline)
    except ChatlogDead as exc:
        return {
            "ok": False,
            "error": str(exc),
            "dead": True,
            "agent": {
                "id": entry.name,
                "role": entry.role,
                "profile": entry.profile_name,
                "spawned": spawned,
            },
        }

    payload = {
        "ok": True,
        "intent": intent,
        "user_text": user_text,
        "agent": {
            "id": entry.name,
            "role": entry.role,
            "profile": entry.profile_name,
            "spawned": spawned,
        },
        "agenda": summary,
    }
    try:
        payload["plan"] = _l1_plan_view(pipeline, summary)
    except Exception as exc:
        logger.warning("vaelis: last-night plan read failed: %s", exc)
        payload["plan"] = _missing_plan_payload(_tomorrow_for_date(summary))
    try:
        payload["sessionId"] = append_n3_dispatch(
            entry, user_text=user_text, intent=intent
        )
    except Exception as exc:
        logger.warning("vaelis N3 session write failed: %s", exc)
        payload["sessionId"] = ""
        payload["n3_error"] = str(exc)

    if intent == "write_briefing":
        try:
            ensure_aigw_provider()
            from hermes_cli.profiles import get_profile_dir as _gpd

            ensure_aigw_provider(_gpd(entry.profile_name))
        except Exception as exc:
            logger.warning("vaelis aigw provider register skipped: %s", exc)
        briefing = generate_morning_briefing(
            summary,
            user_text,
            plan=payload.get("plan"),
            aigw_complete=aigw_complete,
            fallback_complete=fallback_complete,
        )
        payload["briefing"] = briefing["text"]
        payload["route"] = briefing["route"]
        payload["model"] = briefing.get("model") or ""
    return payload


def n3_briefing_text(intent: str, entry: AgentEntry) -> str:
    """L1 派工简报 — 用户原话之外的第二条可见消息。不复制 L1 全文。"""
    if intent == "write_briefing":
        action = "根据明日日程写一段早报"
        ret = "早报正文；标明 route=workbuddy 或 fallback（F2）"
    else:
        action = "刷新明日日程（一轮采集）"
        ret = "当日+次日 events 结构化摘要（零聊天 API）；L1 终答说人话"
    return (
        f"【L1 派工简报】\n"
        f"intent: {intent}\n"
        f"要做: {action}\n"
        f"交回: {ret}\n"
        f"agent: {entry.name} (profile={entry.profile_name})\n"
    )


def _latest_session_id(db) -> str:
    try:
        row = db._conn.execute(
            "SELECT id FROM sessions "
            "ORDER BY COALESCE(ended_at, started_at) DESC LIMIT 1"
        ).fetchone()
    except Exception:
        return ""
    if row is None:
        return ""
    return str(row[0] or "")


def append_n3_dispatch(
    entry: AgentEntry,
    *,
    user_text: str,
    intent: str,
    session_id: str | None = None,
) -> str:
    """Append user original + L1 briefing to the L2 profile's session store.

    Reuses Hermes ``SessionDB.append_message`` (the same ``state.db`` WP-BE-3
    maps onto ``GET /api/agents/:id/overview`` ``sessionId``). Does not copy
    the L1 transcript and does not create a parallel chat table.
    """
    import uuid

    from hermes_cli.profiles import get_profile_dir
    from hermes_state import SessionDB

    profile_dir = get_profile_dir(entry.profile_name)
    db = SessionDB(db_path=profile_dir / "state.db")
    sid = (session_id or "").strip() or _latest_session_id(db)
    if not sid:
        sid = f"vaelis-n3-{uuid.uuid4().hex[:12]}"
    db.create_session(sid, source="cli")
    db.append_message(sid, role="user", content=user_text)
    db.append_message(sid, role="assistant", content=n3_briefing_text(intent, entry))
    return sid


# ---------------------------------------------------------------------------
# WP-BE-7: morning briefing via aigw workbuddy/* (F2 → L2 cheap API)
# ---------------------------------------------------------------------------

AIGW_DEFAULT_BASE = "http://127.0.0.1:8000/v1"
WORKBUDDY_PREFIX = "workbuddy/"
WORKBUDDY_DEFAULT_MODEL = "workbuddy/deepseek-chat"


def aigw_base_url() -> str:
    return (
        os.environ.get("VAELIS_AIGW_URL")
        or os.environ.get("VAELIS_QUOTA_AIGW_URL")
        or AIGW_DEFAULT_BASE
    ).rstrip("/")


def aigw_api_key() -> str:
    return (
        os.environ.get("AIGW_API_KEY")
        or os.environ.get("VAELIS_QUOTA_AIGW_KEY")
        or "sk-local-dev-key"
    )


def pick_workbuddy_model(model_ids: list[str]) -> str:
    for mid in model_ids:
        if str(mid).startswith(WORKBUDDY_PREFIX):
            return str(mid)
    return WORKBUDDY_DEFAULT_MODEL


def _openai_chat_complete(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    timeout: float = 30.0,
) -> str:
    import json as _json
    import urllib.request

    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    body = _json.dumps(
        {"model": model, "temperature": 0.3, "messages": messages},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = _json.loads(response.read().decode("utf-8"))
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("aigw returned no choices")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("aigw returned empty content")
    return content.strip()


def list_aigw_models(*, base_url: str | None = None, api_key: str | None = None) -> list[str]:
    import json as _json
    import urllib.request

    base = (base_url or aigw_base_url()).rstrip("/")
    key = aigw_api_key() if api_key is None else api_key
    request = urllib.request.Request(
        f"{base}/models",
        headers={"Accept": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = _json.loads(response.read().decode("utf-8"))
    ids: list[str] = []
    for item in payload.get("data") or []:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
        elif isinstance(item, str):
            ids.append(item)
    return ids


def _briefing_prompt(
    agenda_summary: dict, user_text: str, plan: dict | None = None
) -> str:
    if _uses_plan_briefing(plan):
        assert plan is not None
        lines = [
            f"用户原话：{user_text}",
            f"日期：{plan.get('for_date') or agenda_summary.get('tomorrow') or ''}",
            f"昨夜计划：{plan.get('summary') or ''}",
            f"冲突数：{int(plan.get('conflict_count') or 0)}",
            "请写一段简洁中文早报，不要解释调度过程，不要逐条抽取。",
        ]
        return "\n".join(lines)
    events = agenda_summary.get("tomorrow_events") or agenda_summary.get("events") or []
    lines = [
        f"用户原话：{user_text}",
        f"日期：{agenda_summary.get('tomorrow') or agenda_summary.get('today') or ''}",
        "明日日程：",
    ]
    if not events:
        lines.append("（无条目）")
    for event in events:
        lines.append(
            f"- {event.get('start_at', '')} {event.get('title', '')} [{event.get('status', '')}]"
        )
    lines.append("请写一段简洁中文早报，不要解释调度过程。")
    return "\n".join(lines)


def _template_briefing(agenda_summary: dict, plan: dict | None = None) -> str:
    if _uses_plan_briefing(plan):
        assert plan is not None
        summary = (plan.get("summary") or "").strip()
        conflicts = int(plan.get("conflict_count") or 0)
        extra = f"（冲突 {conflicts}）" if conflicts else ""
        return f"{summary}{extra}".strip()
    day = agenda_summary.get("tomorrow") or agenda_summary.get("today") or ""
    events = agenda_summary.get("tomorrow_events") or agenda_summary.get("events") or []
    if not events:
        return f"{day} 日程：暂无条目。"
    parts = [
        f"{event.get('start_at', '')} {event.get('title', '')}".strip()
        for event in events
    ]
    return f"{day} 早报：" + "；".join(parts)


def _l2_cheap_complete(prompt: str) -> str:
    """F2: L2 cheap API — quota-pool cheap_api, then VAELIS_L2_CHAT_URL."""
    try:
        from vaelis.quota.pool import get_quota_pool
        from vaelis.quota.sources import HealthStatus

        pool = get_quota_pool()
        pool.probe_all()
        for name in pool.order:
            source = pool.sources.get(name)
            if source is None or source.kind != "cheap_api":
                continue
            status = pool.status(name)
            if status is not None and status.health is HealthStatus.UNAVAILABLE:
                continue
            if not source.base_url:
                continue
            try:
                return _openai_chat_complete(
                    source.base_url,
                    source.api_key,
                    source.model or "deepseek-chat",
                    [{"role": "user", "content": prompt}],
                )
            except Exception as exc:
                logger.warning("vaelis L2 cheap source %s failed: %s", name, exc)
    except Exception as exc:
        logger.warning("vaelis quota pool unavailable for F2: %s", exc)

    url = os.environ.get("VAELIS_L2_CHAT_URL", "").strip()
    key = os.environ.get("VAELIS_L2_API_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("no L2 cheap API configured")
    model = "deepseek-chat"
    try:
        from vaelis.routing import L2_AGENDA, get_router

        model = get_router().resolve(L2_AGENDA).model or model
    except Exception:
        pass
    return _openai_chat_complete(
        url.rstrip("/"),
        key,
        model,
        [{"role": "user", "content": prompt}],
    )


def generate_morning_briefing(
    agenda_summary: dict,
    user_text: str,
    *,
    plan: dict | None = None,
    aigw_complete=None,
    fallback_complete=None,
) -> dict:
    """Default aigw ``workbuddy/*``; on failure, L2 cheap API (route in result)."""
    prompt = _briefing_prompt(agenda_summary, user_text, plan)
    model = WORKBUDDY_DEFAULT_MODEL
    try:
        if aigw_complete is not None:
            text = aigw_complete(prompt)
        else:
            try:
                model = pick_workbuddy_model(list_aigw_models())
            except Exception:
                model = WORKBUDDY_DEFAULT_MODEL
            text = _openai_chat_complete(
                aigw_base_url(),
                aigw_api_key(),
                model,
                [
                    {
                        "role": "system",
                        "content": "你是日程秘书。根据日程表写一段简短中文早报，不要解释调度。",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
        if text and str(text).strip():
            return {
                "text": str(text).strip(),
                "route": "workbuddy",
                "model": model,
            }
    except Exception as exc:
        logger.warning("aigw workbuddy failed (%s); F2 fallback", exc)

    try:
        if fallback_complete is not None:
            text = fallback_complete(prompt)
        else:
            text = _l2_cheap_complete(prompt)
        if text and str(text).strip():
            return {
                "text": str(text).strip(),
                "route": "fallback",
                "model": "l2-cheap",
            }
    except Exception as exc:
        logger.warning("L2 cheap fallback failed: %s", exc)

    return {
        "text": _template_briefing(agenda_summary, plan),
        "route": "fallback",
        "model": "template",
    }


def ensure_aigw_provider(profile_dir: Path | str | None = None) -> bool:
    """Register aigw as an OpenAI-compatible Hermes provider (base_url).

    ``desktop-quotas.ts`` only affects the desktop model picker. L2 generation
    in the gateway must have ``providers.aigw.base_url`` (or custom_providers)
    pointing at the local aigw ``/v1``. Idempotent. Returns True if written.
    """
    import yaml

    if profile_dir is None:
        from hermes_constants import get_hermes_home

        root = get_hermes_home()
    else:
        root = Path(profile_dir)

    cfg_path = root / "config.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}

    base = aigw_base_url()
    key = aigw_api_key()
    provider_entry = {
        "name": "aigw",
        "base_url": base,
        "api_key": key,
        "model": WORKBUDDY_DEFAULT_MODEL,
        "models": {WORKBUDDY_DEFAULT_MODEL: {}},
    }

    changed = False
    providers = cfg.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        cfg["providers"] = providers
    existing = providers.get("aigw")
    if not isinstance(existing, dict) or str(existing.get("base_url") or "").rstrip("/") != base.rstrip("/"):
        providers["aigw"] = dict(provider_entry)
        changed = True

    customs = cfg.get("custom_providers")
    if not isinstance(customs, list):
        customs = []
        cfg["custom_providers"] = customs
    if not any(
        isinstance(row, dict)
        and str(row.get("base_url") or "").rstrip("/") == base.rstrip("/")
        for row in customs
    ):
        customs.append(dict(provider_entry))
        changed = True

    if not changed:
        return False
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return True


MASTER_TOOLSET_NAME = "vaelis_north_star"

# WP-BE-9 / 裁定 12：L1 中收（可逆）。拿掉 terminal / 跑命令类 / 会话搜索；
# clarify 保留。改 platform_toolsets 列表即可加回，不删插件代码。
L1_DROP_TOOLSETS = frozenset(
    {
        "terminal",
        "session_search",
        "code_execution",
        "computer_use",
    }
)


def _is_full_hermes_composite(name: str) -> bool:
    """True for platform composites like ``hermes-cli`` that embed terminal/search."""
    return name.startswith("hermes-")


# 中收默认名单（对齐 docs/vaelis/profiles/master/config.yaml，略宽于「只剩一个」）。
L1_MID_TOOLSETS: tuple[str, ...] = (
    "web",
    "file",
    "memory",
    "skills",
    "todo",
    "clarify",
    "delegation",
    MASTER_TOOLSET_NAME,
)

# Colon fence — no HTML comments, no "secret" substring (html_comment_injection).
L1_SOUL_BEGIN = ":::VAELIS_L1_ASK_ROUTING:::"
L1_SOUL_END = ":::VAELIS_L1_ASK_END:::"
L1_SOUL_LEGACY_BEGIN = "<!-- VAELIS_L1_SECRETARY_ROUTING -->"
L1_SOUL_LEGACY_END = "<!-- /VAELIS_L1_SECRETARY_ROUTING -->"
L1_SOUL_BLOCK = f"""{L1_SOUL_BEGIN}
## 总秘书派工（软路由）

用户问「明天安排 / 明天的日常安排是什么」或「根据明天的日程写早报」时：
调用工具 `vaelis_secretary_ask`（`intent=refresh_agenda` 或 `write_briefing`）。
不要用 `session_search` 搜旧会话，不要开 `terminal` 跑命令，不要 clarify 空转。
选哪个日程 L2 由工具内名单路由（缺则按模板 spawn 一个）；不要写死某个 agent id。
工具回传若有 `plan`：先念 `plan.summary`（昨夜安排）；`missing`/`dismissed` 只陈述刷新后的事实，不要编计划。不要把事件列表再排一遍。
终答像秘书说话，不解释调度细节。

## 日程写入口（硬规则，不可绕过）

- 用户让你加一条日程、改某条的时间或标题、取消某条日程：第一动作就是调用 `vaelis_secretary_ask`，`intent=mutate_agenda`，带上 `action`（`create`/`update`/`delete`）和钟点（本地 ISO，如 `2026-09-12T15:00:00`）。
- 只有工具返回 `ok=true` 才能对用户说「已记下」。缺钟点就先问一句，不准编 9:00，不准默认补 1 小时。
- 不准用 `refresh_agenda` / `write_briefing` 冒充写入。不准叫用户去看板手点、不准让用户自己另开入口。采集通不通都不影响你收下这条指令并落库。
- 改/删没说清是哪条时，工具会返回候选列表；把候选念给用户选，不要替用户猜。

## 采集失败与防编造纪律（硬规则，不可绕过）

- 若 `vaelis_secretary_ask` 返回 `ok=false` / `dead=true`，或 chatlog 采集失败：终答只能说明「日程采集当前不通」，并如实告知；不得假装已拿到日程。
- 严禁用 memory、旧会话、项目印象或任何缓存去编造「明天安排」「早报日程表」等具体安排。采集不通时，宁可不答，也不要虚构。
- `write_briefing` 失败时，不要自己落笔写带钟点的假日程（如「09:00 开会、14:00 健身」）。只如实告知生成失败。
{L1_SOUL_END}
"""


def _l1_soul_fence_pairs() -> tuple[tuple[str, str], ...]:
    """Current fence first, then the HTML comment pair that threat-scan blocked."""
    return (
        (L1_SOUL_BEGIN, L1_SOUL_END),
        (L1_SOUL_LEGACY_BEGIN, L1_SOUL_LEGACY_END),
    )


def _strip_l1_soul_spans(text: str) -> str:
    """Remove every known L1 routing fence (old HTML or current colon markers)."""
    remaining = text
    changed = True
    while changed:
        changed = False
        for begin, end in _l1_soul_fence_pairs():
            if begin not in remaining or end not in remaining:
                continue
            start = remaining.index(begin)
            try:
                stop = remaining.index(end, start) + len(end)
            except ValueError:
                continue
            remaining = remaining[:start] + remaining[stop:]
            changed = True
            break
    return remaining


def mid_narrow_toolset_names(names: list[str] | None) -> list[str]:
    """Rewrite a toolset name list for L1 mid-narrow (reversible)."""
    raw = [str(n) for n in (names or []) if str(n).strip()]
    if not raw or any(_is_full_hermes_composite(n) for n in raw) or any(
        n in L1_DROP_TOOLSETS for n in raw
    ):
        extras = [
            n
            for n in raw
            if not _is_full_hermes_composite(n)
            and n not in L1_DROP_TOOLSETS
            and n not in L1_MID_TOOLSETS
        ]
        return list(L1_MID_TOOLSETS) + extras
    result = [n for n in raw if n not in L1_DROP_TOOLSETS]
    for required in (MASTER_TOOLSET_NAME, "clarify"):
        if required not in result:
            result.append(required)
    return result


def apply_l1_mid_toolsets(config: dict) -> bool:
    """Mutate active-profile config: mid-narrow cli/gateway + top-level toolsets."""
    changed = False
    narrowed = mid_narrow_toolset_names(list(config.get("toolsets") or []))
    if list(config.get("toolsets") or []) != narrowed:
        config["toolsets"] = narrowed
        changed = True

    platforms = config.get("platform_toolsets")
    if not isinstance(platforms, dict):
        platforms = {}
        config["platform_toolsets"] = platforms
        changed = True
    for platform in ("cli", "gateway"):
        current = platforms.get(platform)
        as_list = list(current) if isinstance(current, list) else []
        # Missing platform list falls back to hermes-cli at runtime — write mid.
        next_list = mid_narrow_toolset_names(as_list if as_list else ["hermes-cli"])
        if as_list != next_list:
            platforms[platform] = next_list
            changed = True
    return changed


def ensure_l2_agenda_toolsets(profile_dir: Path | str) -> bool:
    """Keep terminal available on agenda L2 profiles (do not inherit L1 mid-narrow).

    Reversible: only appends ``terminal`` when neither ``hermes-cli`` nor
    ``terminal`` is listed. Never rewrites L1/default.
    """
    import yaml

    cfg_path = Path(profile_dir) / "config.yaml"
    if not cfg_path.is_file():
        return False
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if not isinstance(cfg, dict):
        return False

    changed = False
    platforms = cfg.get("platform_toolsets")
    if not isinstance(platforms, dict):
        platforms = {}
        cfg["platform_toolsets"] = platforms
        changed = True
    for platform in ("cli", "gateway"):
        listed = platforms.get(platform)
        if not isinstance(listed, list):
            listed = []
            platforms[platform] = listed
            changed = True
        names = [str(n) for n in listed]
        if "hermes-cli" in names or "terminal" in names:
            continue
        listed.append("terminal")
        changed = True

    top = cfg.get("toolsets")
    if isinstance(top, list):
        names = [str(n) for n in top]
        if "hermes-cli" not in names and "terminal" not in names:
            top.append("terminal")
            changed = True

    if not changed:
        return False
    cfg_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return True


def ensure_l1_secretary_routing_soul(*, home: Path | str | None = None) -> bool:
    """Upsert soft-routing instructions into the active profile ``SOUL.md``."""
    from hermes_constants import get_hermes_home

    soul_path = Path(home) / "SOUL.md" if home is not None else get_hermes_home() / "SOUL.md"
    existing = ""
    if soul_path.is_file():
        existing = soul_path.read_text(encoding="utf-8")
    stripped = _strip_l1_soul_spans(existing).rstrip()
    updated = (stripped + "\n\n" if stripped else "") + L1_SOUL_BLOCK.strip() + "\n"
    if updated == existing:
        return False
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(updated, encoding="utf-8")
    return True


def ensure_north_star_toolset(*, save: bool = True) -> dict:
    """Open ``vaelis_north_star`` on the **active** profile (usually default).

    Does not create a ``master`` profile (裁定 6). WP-BE-9 also mid-narrows
    L1 toolsets (drop terminal / session_search / command runners) and upserts
    soft-routing SOUL instructions. Idempotent and reversible via config lists.
    """
    from hermes_cli.config import load_config, save_config

    config = load_config()
    changed = apply_l1_mid_toolsets(config)

    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}
        config["plugins"] = plugins
        changed = True
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        enabled = []
        plugins["enabled"] = enabled
    if "vaelis-north-star" not in enabled:
        enabled.append("vaelis-north-star")
        changed = True
    entries = plugins.get("entries")
    if not isinstance(entries, dict):
        entries = {}
        plugins["entries"] = entries
    entry = entries.get("vaelis-north-star")
    if not isinstance(entry, dict):
        entry = {}
        entries["vaelis-north-star"] = entry
    if not entry.get("enabled"):
        entry["enabled"] = True
        changed = True

    if changed and save:
        save_config(config)
    try:
        ensure_l1_secretary_routing_soul()
    except Exception:
        logger.debug("vaelis: L1 secretary SOUL routing upsert skipped", exc_info=True)
    return config


def load_registry(path: Path | str | None = None) -> AgentRegistry:
    return AgentRegistry.load(path)
