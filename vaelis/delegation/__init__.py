"""B4 — L3 delegation guard.

Three pieces, wired together by the ``vaelis-delegation-guard`` plugin:

* :mod:`vaelis.delegation.config`  — ``delegation.*`` knobs B4 owns.
* :mod:`vaelis.delegation.guard`   — process-wide concurrency ceiling with a
  bounded FIFO wait (overflow queues, then degrades to a block message).
* :mod:`vaelis.delegation.quota`   — breaker seam; B3 plugs real sources in.
* :mod:`vaelis.delegation.tracker` — subagent lifecycle → the §5
  ``/api/agents/:id/subagents`` shape.

Explicitly out of scope: mounting HTTP routes. §5 owns the ``/api/agents``
surface; B4 only supplies the data source (``subagents_for_agent``).
"""

from vaelis.delegation.guard import (
    Admission,
    DelegationGuard,
    Lease,
    get_guard,
    set_guard,
)
from vaelis.delegation.quota import (
    BudgetProvider,
    QuotaCircuit,
    QuotaProvider,
    QuotaVerdict,
    get_quota_circuit,
    set_quota_circuit,
)
from vaelis.delegation.tracker import (
    AGENT_STATUSES,
    SubagentRecord,
    SubagentTracker,
    get_tracker,
    set_tracker,
    subagents_for_agent,
)

__all__ = [
    "Admission",
    "AGENT_STATUSES",
    "BudgetProvider",
    "DelegationGuard",
    "Lease",
    "QuotaCircuit",
    "QuotaProvider",
    "QuotaVerdict",
    "SubagentRecord",
    "SubagentTracker",
    "get_guard",
    "get_quota_circuit",
    "get_tracker",
    "set_guard",
    "set_quota_circuit",
    "set_tracker",
    "subagents_for_agent",
]
