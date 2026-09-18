---
name: vaelis-morning-report
description: Build and deliver the Vaelis overnight/morning report (completed, failed, awaiting human). Use after night autonomy or when user asks for 早报.
version: 0.2.0
author: Vaelis
license: MIT
metadata:
  hermes:
    tags: [vaelis, butler, night, report]
---

# Vaelis Morning Report

## Steps

1. Call `vaelis` with `area=ops` `action=morning_report`.
2. Optionally `area=task` `action=board` for fresher counts.
3. Deliver markdown; lead with **awaiting approvals**.
4. Do not auto-approve L2+ items. Use Hermes gateway to deliver — do not invent a notifier.
