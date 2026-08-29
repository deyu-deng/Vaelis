# 术语表（吸收自 BULEPRINT.md / CONTEXT.md）

> **来源**：本文档由 2026-08-24 文档体系整理时吸收生成，内容提炼自已删除的
> `Docs/BULEPRINT.md` 与 `Docs/CONTEXT.md`。术语为强制约定，全仓（代码/文档/模板/LLM 输出）必须遵守，
> 禁止使用"禁止别名"列中的词汇。

## 核心术语（强制，含合规性）

| 术语 | 定义 | 禁止别名 |
|------|------|----------|
| 协调器（Master Agent） | 理解需求、追问澄清、生成 plan.md、调度专业 Agent 的编排者，本身不直接执行具体任务 | Master、主 Agent、中央控制器 |
| 专业 Agent（Sub-Agent） | 执行具体任务的工作者。预置角色：Researcher、Engineer、Publisher、Musician、Videographer、Scout | 子 Agent、从属 Agent、工具 Agent |
| plan.md | 协调器生成的结构化任务计划，含任务列表/状态/依赖，是专业 Agent 的权威执行依据 | 任务单、计划书、待办列表 |
| 轻量调度（Fast-Track Delegation） | Master 经 LangGraph 路由到单个 Agent，但不生成 plan.md、不展开 Kanban，以对话流微交互反馈替代完整状态流 | 快捷路径、快速通道、简版调度 |
| 渐进式升维（Progressive Escalation） | 默认走轻量路径，允许用户事后通过 UI 动作升格为完整 plan.md 流程；仅算力成本过高时主动确认 | 升级、提升、自动升格 |

## 关系模型

- **Session** contains one **Master Agent** and zero or more **Sub-Agents**
- **Master Agent** produces zero or one **plan.md** per task
- A **plan.md** contains one or more **Tasks**
- Each **Task** is assigned to exactly one **Sub-Agent**
- **Fast-Track Delegation** bypasses **plan.md** but still routes through **LangGraph**

## 交互范式

默认轻量调度（Fast-Track Delegation）→ 用户可升格为 plan.md 完整流程（渐进式升维）。

> 注：早期蓝图曾用"操作系统"比喻产品定位，已确认为比喻性表述，实际定位为**智能工作台 / Agent 控制台**。
