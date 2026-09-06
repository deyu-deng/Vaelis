---
name: vaelis-butler-extended
description: Extended invisible butler — email triage, parcels, calendar conflicts, disk hygiene. Uses domain slots and risk gates.
version: 0.2.0
author: Vaelis
license: MIT
metadata:
  hermes:
    tags: [vaelis, butler, email, calendar, disk]
---

# Vaelis Butler Extended

## Steps

1. `vaelis` `area=ops` `action=domain_list` kind=butler.
2. Enqueue with domain default_risk via `area=task` `action=enqueue`.
3. Prefer existing Hermes/Mind integrations for mail/calendar when present.
4. Destructive disk ops need approval (L2+).
