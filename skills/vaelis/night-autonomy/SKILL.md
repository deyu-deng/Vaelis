---
name: vaelis-night-autonomy
description: Night mode tick — run low-risk queued work, hold high-risk, prepare morning report.
version: 0.2.0
author: Vaelis
license: MIT
metadata:
  hermes:
    tags: [vaelis, night, cron]
---

# Vaelis Night Autonomy

Schedule with Hermes **cron** (do not build a new scheduler).

1. `vaelis` `area=ops` `action=night_tick`.
2. If claimed: `area=compute` `action=route` then workers; `area=task` `action=complete` with summary only.
3. Morning: skill `vaelis-morning-report`.
