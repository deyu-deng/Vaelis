# ADR-0007: 日程状态层采用 SQLite，Mind 保持知识真源

- **状态**：Accepted
- **日期**：2026-08-24
- **决策者**：MVP-AI-Secretary-Requirements V0.3（决策⑥）
- **关联**：`specs/agenda-board.md`、`vaelis/north_star/GRILL_FREEZE.md`（Mind 记忆脑条目）

## 上下文与背景

MVP 里程碑 M1 要交付内置日程看板与实时变更通知，核心操作是「按时间范围查询、检测冲突、对比改动前后、回溯证据来源」。

北极星契约已冻结 **Mind 为官方记忆脑**（`memory.provider: mind`，真源为唯一 git remote + `MIND_ROOT`）。由此产生一个歧义：日程与 DDL 这类**运行时状态**是否也该落在 Mind 里？

Mind 的实际形态是 Obsidian markdown + git 同步 + `Loom/scripts/verifier.py` 提交前校验。若把高频变动的日程写进 markdown：查询要靠全文检索、冲突检测困难、每次写入都要过 verifier 与 git 同步，且多写入方并发时必然冲突。

## 决策

**日程/DDL 等运行时状态存 SQLite；Mind 只作为知识与画像真源，接收每日日程摘要。**

- 状态库：SQLite 表 `events`，字段含 `source`（wechat / manual / dingtalk / timetable）、`evidence`（原始消息片段）、`prev_value`（改动前值）、`status`（pending / confirmed / cancelled）。完整 schema 见 `specs/agenda-board.md`。
- Mind 侧：读 `Vault/meta/Persona.md` 与项目状态用于识别辅助；写入仅为每日日程摘要，落 `Loom/`（`Vault/` 禁 AI 元注释）。
- 由此明确：北极星契约里「Mind 是真源」指的是**知识与画像**的真源，不是运行时状态的真源。

## 考虑过的选项

| 选项 | 说明 | 否决/采纳理由 |
|------|------|--------------|
| SQLite 状态层 + Mind 存摘要 | 结构化表承载查询与 diff，知识仍归 Mind | 采纳：查询/冲突检测/证据回溯都是关系型问题，且绕开 verifier 与 git 并发 |
| 全部写入 Mind markdown | 单一存储，无新组件 | 否决：无法高效按时间查询；每次写入过 verifier + git；多写入方并发冲突 |
| JSON 文件（仿 North Star `tasks.json`） | 零依赖，实现最快 | 否决：同一日程反复改期时的并发读写易损坏，且缺索引 |
| 引入外部数据库（Postgres 等） | 能力最强 | 否决：单用户本地场景过重，增加部署与常驻负担 |

## 后果

### 正面影响

- 看板所需的时间范围查询、冲突检测、新旧对比、证据回溯都成为普通 SQL 操作。
- Mind 免于承担高频写入，verifier 与 git 同步保持稳定。
- 职责边界清晰（运行时状态 vs 长期知识），符合深模块原则。

### 负面影响与代价

- 系统出现两处持久化（SQLite + Mind），需要明确单向同步方向（状态 → 摘要 → Mind），否则会出现双真源漂移。
- 未来若需要跨设备同步日程，SQLite 不像 Mind 那样自带 git 同步，需另行设计。
*（内容由AI生成，仅供参考）*
