# Vaelis — 设计 / 架构意图存档

本目录收录产品与架构意图文档。
当前代码库是 Hermes Agent 的上游 fork；**实现状态以 `docs/IMPLEMENTED_FEATURES.md` 为准**。

## 文档索引

| 文件 | 内容 | 注意 |
|---|---|---|
| **`north_star/GRILL_FREEZE.md`** | **Grill 冻结需求真源**（2026-08-09） | **改契约先改这里** |
| **`north_star/`** | 北极星契约全集（风险/架构/API/O3 复用） | 当前产品方向 |
| `ADOPT_KEEP_DROP.md` | Hermes Adopt/Keep/Drop 决策记录 | 决策依据；部分过时（如 Tauri） |
| `CONTEXT.md` | 旧 Plobi 术语 | 历史词汇，勿当实现 |
| `BULEPRINT.md` | 功能清单重建版 | 自标严重过时 |
| `UI_DESIGN_SPEC.md` | 视觉规范参考 | 参考 |
| `AUDIT.md` | 验收审计 + 红线 | 历史 |
| `profiles/master/config.yaml` | Master profile 模板 | 与 north_star 配套 |
| `issues/` | issue / 技术债 backlog | 历史 |

> 旧 Plobi Master/LangGraph/Tauri 叙事已废弃；总指挥产品意图由 `north_star/` + `plugins/vaelis-north-star/` 承接。
