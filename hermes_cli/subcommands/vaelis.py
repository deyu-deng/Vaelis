"""``hermes vaelis`` subcommand parser.

B2: L2 常驻 Agent 注册表 —— ``vaelis agents list / register / spawn``。
Handler 由 main.py 注入（``cmd_vaelis``），薄壳转发到 vaelis.agents.cli。
"""

from __future__ import annotations

from typing import Callable


def build_vaelis_parser(subparsers, *, cmd_vaelis: Callable) -> None:
    """Attach the ``vaelis`` subcommand to ``subparsers``."""
    vaelis_parser = subparsers.add_parser(
        "vaelis",
        help="Vaelis-native ops — resident agents, routing, profiles",
        description=(
            "Vaelis-native operations. Currently: the L2 resident agent "
            "registry (B2) — one persistent profile per project, "
            "role→model routing from config, independent sessions."
        ),
    )
    vaelis_subparsers = vaelis_parser.add_subparsers(dest="vaelis_action")

    # ------------------------------------------------------------------ #
    # vaelis agents — L2 resident registry
    # ------------------------------------------------------------------ #
    agents_parser = vaelis_subparsers.add_parser(
        "agents",
        help="L2 resident agent registry (B2)",
        description=(
            "Manage the L2 resident agent registry: one persistent profile "
            "per project, role→model routing (ADR-0011), independent "
            "sessions. Registry lives at $HERMES_HOME/vaelis/projects.yaml."
        ),
    )
    agents_sub = agents_parser.add_subparsers(dest="agents_action")

    agents_sub.add_parser("list", help="List registered resident agents + routing status")

    register = agents_sub.add_parser(
        "register",
        help="Add or update a registry entry (no profile side effects)",
    )
    register.add_argument("name", help="Agent name (also the default profile name)")
    _add_entry_args(register)

    spawn = agents_sub.add_parser(
        "spawn",
        help="Materialize a profile + model routing for a registered agent",
        description=(
            "Ensure the agent's profile exists (create if missing, cloning "
            "config/.env/skills from the active profile), write the "
            "role→model route into the profile's vaelis/models.json, "
            "verify ADR-0011, and sync config.yaml. If the agent is not "
            "registered yet, --role/--model etc. register it first."
        ),
    )
    spawn.add_argument("name", help="Agent name (must match a registry entry)")
    spawn.add_argument(
        "--clone-from",
        metavar="PROFILE",
        default=None,
        help="Source profile to clone for a fresh spawn (default: active profile)",
    )
    _add_entry_args(spawn)

    vaelis_parser.set_defaults(func=cmd_vaelis)


def _add_entry_args(parser) -> None:
    """Shared registry-entry fields for register/spawn."""
    parser.add_argument(
        "--role",
        default=None,
        help="Agent role (l1_secretary / l2_agenda / l2_planner / l2_project / custom)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Hermes profile name (default: the agent name)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Model provider override (default: routing default)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model override (default: routing default)",
    )
    parser.add_argument(
        "--mind-subtree",
        default=None,
        help="Mind project subtree relative to MIND_ROOT, e.g. Vault/projects/Vaelis",
    )
    parser.add_argument(
        "--skills",
        default=None,
        help="Comma-separated skill names the resident agent preloads",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="One-line description of what this agent closes the loop on",
    )
