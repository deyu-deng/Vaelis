---
name: vaelis-quota-alert
description: Warn when AI free-tier or paid subscription quotas are low. Use for 额度预警 / subscription burn alerts.
version: 0.2.0
author: Vaelis
license: MIT
metadata:
  hermes:
    tags: [vaelis, butler, quota, aigw]
---

# Vaelis Quota Alert

## Steps

1. Read aigw / desktop quota signals (reuse aigw — do not scrape if API exists).
2. If low: `vaelis` `area=task` `action=enqueue` goal="Quota alert: …" risk=L0.
3. `vaelis` `area=preview` `action=push` priority=resource.
4. `vaelis` `area=compute` `action=route` to steer work off exhausted surfaces.
