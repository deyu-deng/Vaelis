# Specs — 规格文档索引

> 本文档固化 Vaelis 文档体系中的**规格引用链**，是理解"最终形态 vs MVP 目标"的入口。
> 建立于 2026-08-24 文档体系整理（见 `adr/0001-documentation-strategy.md`）；2026-08-24 随 MVP V0.3 更新。

## 引用链（阅读顺序）

```
顶层 Spec（最终形态愿景）
  └─ AI-Native-Life-System-Spec-V1.md   ← Vaelis 完整愿景（外部，位于仓库根 Docs/）
        ↓ 约束
north_star 契约（最终形态 · 需求真源）
  └─ ../vaelis/north_star/GRILL_FREEZE.md   ← 冻结清单（三级 Agent / 风险门禁 / Mind / HID）
        ↓ 派生短期目标
MVP 规格（短期验证性功能 · 真源）
  └─ MVP-AI-Secretary-Requirements.md   ← MVP 需求真源，V0.3 拆为 M1/M2/M3
        ↓ 落地
实现级规格（本目录 specs/）
  ├─ agenda-board.md                    ← M1：日程状态层（SQLite）+ Electron 内置看板
  ├─ MIND_ADAPTER_PLAN.md               ← Mind 适配器计划
  ├─ openai-api-server.md               ← OpenAI API 兼容服务规格
  └─ streaming-support.md               ← 流式支持规格
```

## 当前里程碑

| 里程碑 | 范围 | 主规格 |
|---|---|---|
| **M1（进行中）** | 采集 → SQLite 状态 → 内置看板 + 钉钉通知 | `MVP-AI-Secretary-Requirements.md` §2–§8、`agenda-board.md` |
| M2 | 规划层（每晚生成次日计划） | 待补 |
| M3 | 执行层 + 验证层（含 L3 GUI 执行体、Pico 优先级队列） | 待补 |

## ADR 映射

| ADR | 主题 |
|---|---|
| 0001 | 文档体系策略（Diátaxis + ADR） |
| 0002 | 通知通道：钉钉机器人（**已修订**：Stream 双向；看板范围移交 0008） |
| 0003 | chatlog 开机自启常驻 |
| 0004 | 钉钉本地解密采集（预留，未落地） |
| 0005 | 增量识别：规则过滤 + 模型确认 |
| 0006 | 底座 Hermes 不迁移（**已修订**：MVP 明确不引入 LangGraph 及触发条件） |
| 0007 | 日程状态层用 SQLite，Mind 保持知识真源 |
| 0008 | 内置日程看板进 MVP，Electron 原生页面 |
| 0009 | 日程变更「待确认 + 钉钉双向确认」 |
| 0010 | 采集白名单与送模型的数据边界 |
| 0011 | 三级 Agent 架构与分层模型路由 |

## 目录约定

| 目录/文件 | 内容 | 状态 |
|-----------|------|------|
| `specs/` | 实现级规格（当前目录） | 活跃 |
| `../vaelis/north_star/` | 最终形态契约（冻结清单 / 风险门禁 / API / 架构 / OSS 复用） | 活跃 · 保留原位 |
| `MVP-AI-Secretary-Requirements.md` | MVP 需求真源 | 活跃 · 本目录内 |
| `AI-Native-Life-System-Spec-V1.md` | 顶层愿景 Spec | 活跃 · 外部引用 |

## 说明

- **最终形态**：以 `north_star/` 契约 + 顶层 Spec 为准。
- **MVP 目标**：以 `MVP-AI-Secretary-Requirements.md` 为真源，本目录其余文件为对应实现级规格。
- 新增规格先判断归属（最终形态 → north_star；MVP 功能 → 本目录；纯实现细节 → 代码注释/README），并使用 `../templates/spec-template.md`。
