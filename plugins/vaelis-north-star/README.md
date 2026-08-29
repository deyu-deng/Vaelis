# vaelis-north-star

Deep edge module for the Vaelis North Star. **Reuse Hermes**; expose a narrow API.

## Public interfaces only

| Surface | What |
|---|---|
| Agent tool | `vaelis` (`area` + `action`) |
| HTTP | `/api/plugins/vaelis-north-star/*` |
| Docs | [`docs/vaelis/north_star/API.md`](../../docs/vaelis/north_star/API.md) |

Do **not** import `lib/queue.py`, `lib/hid/*`, etc. from Electron.

## Enable

```yaml
plugins:
  enabled:
    - vaelis-north-star
```

Include toolset `vaelis_north_star` (see `docs/vaelis/profiles/master/config.yaml`).

## Reuse

- Board collaboration → Hermes **kanban** (mirrored on enqueue)
- Messaging / mobile → Hermes **gateway** + `/vaelis …`
- Schedules → Hermes **cron** + `skills/vaelis/*`
- Antigravity → **aigw**
- Marvis GUI → HID (owned here)

## HID

Default mock-safe. Real Pico: `VAELIS_PICO_SERIAL` + `vaelis` `area=compute action=hid_run mock=false`.
