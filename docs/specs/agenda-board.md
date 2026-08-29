# 日程状态层与内置看板

- **版本**：v0.1
- **日期**：2026-08-24
- **状态**：已采纳
- **关联 ADR**：ADR-0007（SQLite 状态层）、ADR-0008（看板进 MVP / Electron 原生）、ADR-0009（待确认语义与钉钉确认）、ADR-0010（白名单采集）、ADR-0011（Agent 分层与模型路由）
- **上游**：`MVP-AI-Secretary-Requirements.md` V0.3 里程碑 M1

## 背景

M1 要交付「群里说明天调课 → 15 分钟内手机响、看板变」。这需要一份**可按时间查询、可 diff、可追溯证据**的日程状态，以及一个用户每天真会看的界面。

Mind 是知识与画像的真源，但它是 Obsidian markdown + git + verifier，不适合承载高频写入的运行时状态；因此状态层独立为 SQLite，Mind 只接收每日摘要（ADR-0007）。

## 用户故事

- 作为用户，我希望打开桌面端就能看到今天和明天的全部安排（含我手动加的），以便不再翻聊天记录。
- 作为用户，我希望群里说改期后，看板上那条日程显示「待确认」和新旧对比，以便我一眼判断该不该接受。
- 作为用户，我希望手机收到通知后回一句话就能确认或忽略，以便不必回到电脑前。
- 作为用户，我希望每条系统写入的日程都能点开看到原始消息，以便判断它是不是模型看错了。

## 模块边界（硬约束）

### 后端：自成一包，不散落

```
vaelis/agenda/
  store.py      # 仅 SQLite 读写（schema、迁移、查询）；不含业务判断
  service.py    # 业务：待确认语义、变更 diff、证据装配、Mind 摘要触发
  router.py     # 薄 HTTP 适配层：请求校验 → service → 响应
  rules.py      # 本地规则过滤（关键词/时间表达式），不调模型
```

- **深模块**：对外只暴露 `service.py` 的函数与 `router.py` 的 HTTP 面；`store.py` / `rules.py` 属实现细节，不被其他模块直接 import。
- **无模型依赖**：`store` / `rules` / `router` 不得调用任何 LLM；模型确认由 L2 日程秘书调用 `service` 完成。
- 采集器（chatlog 客户端）与本包解耦：采集只产出「候选事件」交给 `service`，不直接写库。

### 前后端分离

- 后端提供 REST（见下）；前端**不得**直接读 SQLite 或 import Python 模块。
- 前端调用统一走 `apps/desktop/src/hermes.ts` 新增的函数，形如：

```ts
export function getAgenda(from: string, to: string): Promise<AgendaEvent[]> {
  return window.hermesDesktop.api<AgendaEvent[]>({ path: `/api/agenda?from=${from}&to=${to}` })
}
```

- **禁止**在页面里写裸 `fetch()`。房规是 `window.hermesDesktop.api({ path })`（参照 `hermes.ts` 的 `getCronJobs`）。
- 既有 `apps/desktop/src/lib/vaelis-api.ts` 使用裸 fetch，偏离此约定，需在实现本规格时一并收敛。

### 设计风格一致

看板必须遵守 `apps/desktop/DESIGN.md`，落地时逐项对齐它的「Before you add something」清单：

| 需求 | 复用的既有primitive |
|---|---|
| 页面骨架 | `OverlaySplitLayout` / `OverlaySidebar` / `OverlayMain`（cron、profiles 同款） |
| 列表与行 | `PanelList` / `PanelListRow` / `ListRow` |
| 状态徽标（待确认/已确认/已取消） | `PanelPill` + `PanelPillTone`（good / warn / bad / muted） |
| 按钮 | `components/ui/button.tsx` 的 `variant` + `size`，不覆盖 padding/radius |
| 加载 / 空 / 错误 | `Loader` / `EmptyState` / `ErrorState` |
| 图标 | `Codicon` 单一图标集 |
| 页面留白 | `PAGE_INSET_X`，不硬编码 `px-6` |
| 颜色与阴影 | 只用 `--ui-*` / `shadow-nous` / `--stroke-nous` token，零裸色值 |
| 文案 | `useI18n()`，**四语言同步**（en / ja / zh / zh-hant） |
| 状态管理 | 特性自有 nanostores 原子（`src/store/agenda.ts`），渲染用 `useStore` |

风格红线：扁平不套盒、不加行分隔线、不自建搜索框（用 `SearchField`）。

## 数据模型（SQLite）

表 `events`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | `evt_<uuid12>` |
| `title` | TEXT | 事件标题 |
| `start_at` | TEXT | ISO8601 本地时区 |
| `end_at` | TEXT NULL | 可空（DDL 类只有截止点） |
| `kind` | TEXT | `meeting` / `ddl` / `class` / `task` |
| `status` | TEXT | `pending` / `confirmed` / `cancelled` |
| `source` | TEXT | `wechat` / `manual` / `dingtalk` / `timetable` |
| `evidence` | TEXT NULL | JSON：`{msg_id, talker, sent_at, snippet}` |
| `prev_value` | TEXT NULL | JSON：改动前的 `{title,start_at,end_at}`，用于看板新旧对比 |
| `confirm_seq` | INTEGER NULL | 钉钉确认用短序号（见下） |
| `created_at` / `updated_at` | TEXT | ISO8601 |

索引：`(start_at)`、`(status)`。

写入规则：

- `source=manual` 直接落 `confirmed`（用户手输即事实）。
- `source=wechat` 一律落 `pending`，并在改动既有事件时填 `prev_value`。
- `evidence` 只存**命中的单条消息片段**，不存整段上下文（隐私边界，ADR-0010）。

## HTTP API

挂在 `hermes serve` 后端的核心路由（不依赖插件开关）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/agenda?from=&to=` | 按时间范围查事件（默认今天+明天） |
| POST | `/api/agenda` | 手动新增（落 `confirmed`） |
| PATCH | `/api/agenda/{id}` | 手动修改 |
| DELETE | `/api/agenda/{id}` | 删除 |
| POST | `/api/agenda/{id}/confirm` | 确认 `pending` → `confirmed` |
| POST | `/api/agenda/{id}/dismiss` | 忽略 `pending`（回滚到 `prev_value` 或删除新建项） |
| GET | `/api/agenda/pending` | 待确认列表（钉钉推送与看板角标共用） |

## 钉钉确认协议

1. 产生 `pending` 事件时分配 `confirm_seq`（当日递增的小整数）。
2. 钉钉 Stream 机器人推送：标题、新旧对比、证据片段、`回复「确认 3」或「忽略 3」`。
3. 用户文本回复 → 机器人解析 `确认|忽略 + 序号` → 调用对应 REST 接口。
4. `confirm_seq` **24 小时有效**，过期回复提示改用看板处理。
5. 无法解析的回复不猜测，回一条用法提示。

## 验收标准

- [ ] `vaelis/agenda/` 四文件分层落地，`store` / `rules` 无任何 LLM 调用
- [ ] `events` 表建表与迁移可重复执行（幂等）
- [ ] 七个 REST 接口全部可用，参数非法时返回 4xx 而非 500
- [ ] 桌面看板显示今天+明天，`pending` 条目带徽标与新旧对比
- [ ] 手动增/改/删在 10 秒内反映（轮询 5–10s）
- [ ] 前端所有请求经 `hermes.ts`，页面内零裸 `fetch`
- [ ] UI 仅使用 DESIGN.md 列出的 primitive 与 token，无裸色值/无 padding 覆盖
- [ ] 四语言文案齐全
- [ ] 钉钉回复 `确认 N` / `忽略 N` 能落定，过期序号有明确提示
- [ ] `evidence` 可在看板上点开查看原始消息片段

## 取舍（Trade-offs）

- **选核心 `/api/agenda/*` 而非插件路由**：看板是每天要用的一等功能，若挂在 `vaelis-north-star` 插件路由下，会依赖 `plugins.enabled` 开关，用户一旦没开就整块消失。代价是它不像 North Star 那样"能力全在边缘"，需要在核心多一个路由挂载点。
- **选轮询而非 SSE/WebSocket**：5–10 秒轮询对单用户桌面完全够用，省掉推送连接的重连与鉴权复杂度。代价是最坏 10 秒延迟（验收标准已按此写）。
- **`prev_value` 只存一层**：不做完整变更历史。代价是连续多次改期只能看到最近一次的旧值；需要审计再上事件流表。
- **不做周/月视图**：M1 只做今天+明天。代价是开学后课表接入时需要补视图。

## 未决问题（Open Questions）

- 时区固定 `Asia/Shanghai` 还是读系统时区？（M1 暂按系统时区，跨时区场景未验证）
- 同一事件被多个来源同时改动的合并策略（M1 按"后到覆盖 + 保留 prev_value"，冲突面窄时够用）
- 课表导入的去重键（9 月接入时定）

## 关联 ADR

- ADR-0007：状态层为何是 SQLite 而不是 Mind markdown
- ADR-0008：看板为何进 MVP、为何是 Electron 原生页面
- ADR-0009：`pending` 语义与钉钉双向确认
- ADR-0010：`evidence` 只存片段的隐私边界
- ADR-0011：谁来调模型（L2 日程秘书），谁不许调（本包）
*（内容由AI生成，仅供参考）*
