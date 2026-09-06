---
name: vaelis-passive-learn
description: Observe repeated human/agent operations and draft Skills for human confirmation. Do not auto-install Skills.
version: 0.2.0
author: Vaelis
license: MIT
metadata:
  hermes:
    tags: [vaelis, learning, skills]
---

# Vaelis Passive Learn

## Steps

1. `vaelis` `area=ops` `action=learn_observe` with title + steps.
2. `action=learn_drafts` after repeats.
3. Human approves → `action=learn_resolve` approve=true.
4. Materialize with Hermes `skill_manage` only after approval.
