# ADR-0008: 内置日程看板进入 MVP，采用 Electron 原生页面

- **状态**：Accepted
- **日期**：2026-08-24
- **决策者**：MVP-AI-Secretary-Requirements V0.3（决策⑦）
- **关联**：修订 ADR-0002 的范围划分；`specs/agenda-board.md`；`apps/desktop/DESIGN.md`

## 上下文与背景

ADR-0002 原本把「桌面端原生计划看板」划给正式版，MVP 只用钉钉机器人通知过渡。后续需求明确：MVP 就要有**内置日程看板**，且微信/钉钉消息导致日程改动时要**实时更新看板 + 手机通知**。

界面落点存在三种可能，且有一个关键事实约束选择：**Electron 桌面端不渲染 dashboard 插件**——`apps/desktop/src` 中没有任何 dashboard 插件页的接线，`plugins/kanban/dashboard/` 那类插件页只出现在浏览器 dashboard 中。

## 决策

**日程看板进入 MVP（里程碑 M1），实现为 Electron 桌面端原生页面。**

- 位置：`apps/desktop` 新增 overlay 路由，结构参照既有 `apps/desktop/src/app/cron/index.tsx`。
- 数据访问：经 `apps/desktop/src/hermes.ts` 调用核心 REST `/api/agenda/*`（房规是 `window.hermesDesktop.api({ path })`，**禁止**页面内裸 `fetch`）。
- 刷新：5–10 秒轮询，不引入 SSE / WebSocket。
- 交互：支持手动增 / 改 / 删；事件带 `source` 区分来源（wechat / manual / dingtalk / timetable）。
- 视觉：严格遵守 `apps/desktop/DESIGN.md`，复用既有 primitive（`OverlaySplitLayout`、`PanelList`、`PanelPill`、`Button`、`Loader`、`EmptyState`、`ErrorState`、`Codicon`），仅用设计 token，四语言文案同步。

本 ADR **修订** ADR-0002 的范围表述：看板不再是正式版专属，钉钉机器人与内置看板在 MVP 阶段并存（钉钉负责离桌通知与确认，看板负责在桌全景）。

## 考虑过的选项

| 选项 | 说明 | 否决/采纳理由 |
|------|------|--------------|
| Electron 原生页面 | 桌面端新增 overlay 路由 | 采纳：与「Vaelis 独立产品/未来独立移动端」方向一致，是每日入口 |
| 浏览器 dashboard 插件页 | 仿 `plugins/kanban/dashboard/` | 否决：桌面端根本不渲染插件页，日常入口会落在 App 之外 |
| 复用预览轨渲染 HTML 日程 | 每日把日程渲染成产物推预览面板 | 否决：不可交互、无法承载手动增删改与待确认操作 |
| 只读看板 | 仅展示消息抽取结果 | 否决：用户大部分安排不在聊天里（自定计划、课表），只读看板会长期近乎空白，改动率指标也无从统计 |

## 后果

### 正面影响

- 用户每天有一个真实会看的入口，日程与待确认项集中呈现。
- 手动录入让看板成为完整日程真源，为 M2 规划层提供可用输入。
- 复用既有设计系统与 overlay 骨架，无需新建壳层。

### 负面影响与代价

- MVP 需要投入前端工作量（React 页面 + 四语言文案），比纯通知方案重。
- 核心路由多一个挂载点（`/api/agenda/*` 不走插件系统），与「能力全在边缘」的原则有偏离；这是为避免日常功能依赖 `plugins.enabled` 开关而主动接受的代价。
- 轮询带来最长 10 秒延迟，验收标准需按此设定。
*（内容由AI生成，仅供参考）*
