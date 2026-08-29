# Vaelis North Star — Public Interface

Deep-module contract: **simple surface, rich implementation**.  
Consumers must use only the interfaces below. Do not import `plugins/vaelis-north-star/lib/*` from Electron or other UI code.

契约真源：[GRILL_FREEZE.md](./GRILL_FREEZE.md)。

## Design principles

1. **Reuse first (O3)** — Survey mature GitHub projects before building; not limited to the current agent substrate. See [OSS_REUSE.md](./OSS_REUSE.md).
2. **Brand** — Product is Vaelis; substrate pieces are replaceable.
3. **FE/BE separation** — UI talks HTTP (`/api/plugins/vaelis-north-star/*` and future App APIs). Agent talks one deep tool (`vaelis`) unless a slice explicitly adds more.
4. **Narrow Master (W1)** — Domain packages may be heavy; Master only sees dispatch / status / preview / approval.
5. **Mind** — Official memory brain via `memory.provider: mind` + `MIND_ROOT`; never dump the whole vault into Master context.

## Reuse map (examples — always re-survey)

| Need | Prefer surveying |
|---|---|
| Collaboration board | Existing board in current substrate **or** better OSS after O3 survey |
| Messaging / DingTalk | Gateway adapters; ultimate surface = Vaelis App |
| Schedules | Existing cron **or** better OSS scheduler |
| Sub-agents | Existing delegation **or** better orchestrator OSS |
| Protocol free tier | aigw / OpenDesign-style adapters |
| Desktop preview | Existing preview rail + preview-bus |
| Knowledge / memory | **Mind** (official) |
| Marvis GUI-only | HID worker (owned); captcha = human (C1) |

## Agent tool (backend → model)

**Name:** `vaelis`  
**Toolset:** `vaelis_north_star`

```json
{ "area": "task|compute|preview|ops", "action": "<verb>", "...params": "..." }
```

### `area=task`

| action | purpose |
|---|---|
| `enqueue` | Create risk/stage task (L0 / L1a / L1b / L2–L4) |
| `board` | Counts + awaiting human |
| `get` | One task |
| `approve` / `reject` | Human gate (DingTalk / App / desktop) |
| `complete` / `update` | Finish or patch (Master-safe summary) |
| `stage_status` / `stage_advance` / `stage_approve` | Stage gates (code + docs first) |

### `area=compute`

| action | purpose |
|---|---|
| `route` | surface → `hid` \| `aigw` \| `local` |
| `hid_status` | Devices + screen lock |
| `hid_run` | Pico/Marvis/Cursor/browser job |

### `area=preview`

| action | purpose |
|---|---|
| `push` | Auto bus (artifact > progress > resource) |
| `list` / `latest` | Read bus |

### `area=ops`

| action | purpose |
|---|---|
| `master_plan` / `master_summarize` | Clean Master helpers |
| `morning_report` / `night_tick` | Night autonomy + K3-aware resume |
| `mobile_board` / `mobile_instruct` | Phone command surface (DingTalk P1 → App) |
| `domain_list` / `domain_register` | Domain slots (D3) |
| `diagnose` | L4 proposals (U1 human merge) |
| `learn_observe` / `learn_drafts` / `learn_resolve` | Passive Skill drafts (3× → human approve) |

## HTTP API (frontend → backend)

Base: `/api/plugins/vaelis-north-star`  
Auth: dashboard session token (same as other plugin APIs).  
Future Vaelis App should consume the same resource model (board / task / preview / ops).

| Method | Path | Maps to |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/board` | `task(board)` |
| POST | `/task` | `task(...)` |
| POST | `/compute` | `compute(...)` |
| GET/POST | `/preview` | `preview(...)` |
| POST | `/ops` | `ops(...)` |
| GET | `/morning-report` | `ops(morning_report)` |

## DingTalk (P1 mobile)

Commands / bot flows map to the same approve / instruct / board / report actions.  
Payload richness: **V2** — text summary + image/file thumbnails; no remote mouse.

## Private

`lib/*` internals are not a public interface. Stable surface = façade methods + this document.
