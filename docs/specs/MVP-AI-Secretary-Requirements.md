---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 67e28a0cadea4c0368daeffdef023791_95bcf5cb9f6c11f1a238525400e6dd8f
    ReservedCode1: h3qflHNywKIe3q/RI6hZpw66w35zJAh4596wgzqCNvty+j5OH7rrKT2ljIwZ7x69+vzaepluiR5UcGOgTmTjeKxMB9bw2iMc4b0omgRIDvsLDhBzu/mDzGq95K5bWgUl32HlTfXitUIRPMZLDoMgk6tzlSFQWlTi6N/wCR3FmqNoEaYhVlTg6Et613s=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 67e28a0cadea4c0368daeffdef023791_95bcf5cb9f6c11f1a238525400e6dd8f
    ReservedCode2: h3qflHNywKIe3q/RI6hZpw66w35zJAh4596wgzqCNvty+j5OH7rrKT2ljIwZ7x69+vzaepluiR5UcGOgTmTjeKxMB9bw2iMc4b0omgRIDvsLDhBzu/mDzGq95K5bWgUl32HlTfXitUIRPMZLDoMgk6tzlSFQWlTi6N/wCR3FmqNoEaYhVlTg6Et613s=
---

# Vaelis MVP：AI 秘书系统需求规格
**版本**: V0.3
**日期**: 2026-08-24
**状态**: 范围已收敛为里程碑 M1（采集 → 状态 → 看板 → 通知）
**关联**: `AI-Native-Life-System-Spec-V1.md`（顶层构想）→ `vaelis/north_star/GRILL_FREEZE.md`（最终形态契约）→ 本文档（MVP 真源）
**关联 ADR**: ADR-0002（修订）、ADR-0003、ADR-0004、ADR-0005、ADR-0006（修订）、ADR-0007、ADR-0008、ADR-0009、ADR-0010、ADR-0011
**关联 spec**: `agenda-board.md`（看板与状态层实现级规格）

---

## 1. 背景与目标

Vaelis 定位为**贾维斯式主动型 AI 秘书**。MVP 验证核心命题：

> 系统能实时吸收用户的社交消息（微信/钉钉/AI 聊天），结合项目进度与个人日程，每晚生成次日计划；第二天自主推进项目、验证产出、更新文档；对时效性消息（改期/突发 DDL）实时通知用户。

**V0.3 的关键变化**：完整命题拆为三个里程碑，**当前只做 M1**。原 V0.2 把五层闭环作为单一验收单元，会导致每层长期停在半成品状态、用户拿不到任何可验收成果（详见 §9 变更记录）。

## 2. 里程碑拆分

| 里程碑 | 范围 | 状态 |
|---|---|---|
| **M1**（当前） | ① 采集 → ② 结构化状态 → 看板 + ⑥ 通知 | 进行中 |
| M2 | ③ 规划层（每晚生成次日计划） | 未开始 |
| M3 | ④ 执行层 + ⑤ 验证层（自主推进项目、产物校验） | 未开始 |

M1 选择依据：通知能力（钉钉）在底座中**已实现**、chatlog 服务**已常驻**，M1 是唯一能在短期内每天产生真实价值的组合（"群里说明天调课，15 分钟内手机响、看板变"），并天然积累 M2 规划层所需的数据。

## 3. M1 成功标准（可测量）

1. **改动率**：系统维护的日程条目中，用户手动删除或修改的比例 ≤ 20%（连续 7 天统计）。
   - 采集方式：用户对"待确认"条目的确认/忽略动作即数据，无需额外记录（见 ADR-0009）。
   - 该指标替代 V0.2 的"计划吻合率 ≥ 80%"——后者的分母"用户实际安排"缺少 ground truth 采集口，不可测量。
2. **时效性**：时效性消息（会议改期、DDL 变更）在 **15 分钟内**识别并推送到手机。
3. **看板可用性**：看板显示当日与次日全部日程（含手动录入项），日程变更后 10 秒内在看板可见。

## 4. M1 范围

### 4.1 范围内
- **采集层**：chatlog（`127.0.0.1:5030`）增量拉取 + Webhook 接入调度；**白名单**会话（见 ADR-0010）
- **状态层**：SQLite 结构化日程状态（events 表，含来源与证据字段，见 ADR-0007 与 `agenda-board.md`）
- **看板**：Electron 桌面端原生日程页面，可手动增删改（见 ADR-0008）
- **通知层**：钉钉 Stream 模式机器人，双向——推送 + 文本确认（见 ADR-0002 修订、ADR-0009）
- **画像**：Mind 窄切读写（读画像/项目状态辅助识别，写每日日程摘要），见 ADR-0011
- **Agent 分层**：L1（统筹）/ L2（日程秘书）分离 + 角色→模型路由，见 ADR-0011

### 4.2 范围外
- **M2**：每晚 20:00 规划生成
- **M3**：自主推进项目、产物验证、progress.md 更新
- 课表接入（未开学，9 月补充；schema 已预留 `source=timetable`）
- 钉钉消息采集（学校无开放 API，方法已研究未落地；预留 `collect_dingtalk()` 抽象，见 ADR-0004）
- L3 专能子 Agent、GUI 闭源软件驱动、Pico 单设备优先级队列（属最终形态，M3 实现，见 ADR-0011）
- LangGraph 编排（MVP 明确不引入，见 ADR-0006 修订）
- 深夜自治、被动学习、信息猎犬（见 north_star 契约）

## 5. 信息源调研结论

### 5.1 微信：chatlog 工具链

| 项 | 结论 |
|---|---|
| 工具 | `D:\Tools\wechat\chatlog\chatlog.exe` v0.5.2（8/19 部署） |
| 模式 | 本地数据库直读解密，`auto_decrypt: true`，非注入式 |
| HTTP 服务 | `127.0.0.1:5030`，**已开机自启常驻**（Startup 目录 `chatlog_autostart.vbs`，隐藏窗口启动） |
| 配置位置 | `C:\Users\xgbc\.chatlog\chatlog.json`（history[0].http_enabled=true、http_addr=127.0.0.1:5030、auto_decrypt=true；必须无 BOM 的 UTF-8） |
| 核心 API | `GET /api/v1/chatlog?time=YYYY-MM-DD[~YYYY-MM-DD]&talker=&sender=&keyword=&format=`，**time 与 talker 必填**；另有 `/api/v1/contact`、`/chatroom`、`/session`、`/image`、`/voice`、`/video`、`/file`、`/data`、`/health` |
| 增量能力 | `time` 按日期过滤增量拉取；Webhook 新消息回调，本地延迟约 13s |
| MCP 支持 | 内置 `/mcp`（Streamable HTTP）与 `/sse` |
| 真实缺口 | ① ~~5030 未常驻~~ ✅ 已落地 ② **仓库内零消费代码**：无 5030 客户端、无增量拉取脚本、无 Webhook 接收端 ③ 消费侧旧 wechat-cli 路径失效 |

**结论**：工具侧就绪，**M1 的全部采集工作量在消费侧**（客户端 + 白名单过滤 + 调度接入）。

### 5.2 钉钉
- 学校组织无开放平台 API 权限；参考 `dingtalk-exporter`（本地解密 V2/V3 SQLite、WAL 增量、JSON 导出）
- **M1 处理**：仅作为**通知出口**（Stream 机器人）；消息**采集**不在 M1，预留 `collect_dingtalk()`

### 5.3 课表
未开学，无数据。9 月接入教务系统导出，M1 范围外，schema 预留来源枚举。

### 5.4 AI 会话历史
本运行时即产出来源，可读文件/API，归入画像层输入；M1 不作为日程来源。

## 6. 架构

### 6.1 五层闭环（最终 MVP 形态，M1 只覆盖 ①②⑥ + 看板）

```
① 采集层    chatlog(5030) 增量/Webhook · 白名单 → 钉钉采集(预留) → 项目文件状态     【M1】
     ↓ 结构化事件
② 状态层    SQLite events（日程/DDL，含 source + evidence + prev_value）            【M1】
            Mind：知识与画像真源（读画像；写每日摘要，经无模型串行写入服务）        【M1 窄切】
     ↓
   看板      Electron 原生页面，可手动增删改，10s 内反映变更                          【M1】
   通知      钉钉 Stream 机器人：推送 + 文本确认                                      【M1】
     ↓
③ 规划层    每晚 20:00：读次日日程 → 冲突检测 → 生成明日计划（每条带证据）           【M2】
     ↓
④ 执行层    按计划派 L2/L3 推进项目 → 产物落盘                                       【M3】
     ↓
⑤ 验证层    检查产物 → 更新 progress.md / plan.md → 失败回报"卡住"                   【M3】
```

### 6.2 事件驱动 + 定期巡检双轨
- **事件轨道**：chatlog Webhook 新消息 → **本地**规则过滤（周几/几点/截止/改期/开会/DDL）→ 命中则模型确认 → 写入 SQLite（状态 `pending`）→ 钉钉通知
- **巡检轨道**：每 **10 分钟**增量拉取补漏（Webhook 漏消息兜底）
  - V0.2 用 30 分钟巡检，与 15 分钟 SLA 自相矛盾；本版压到 10 分钟以自洽

### 6.3 Agent 分层（三级，见 ADR-0011）

| 层 | 角色 | 模型 | M1 实例 |
|---|---|---|---|
| L1 | 常驻秘书，统筹全局，与 Mind 深度结合 | 市面最好（当前 Kimi K3） | 你偶尔对话的秘书；看板异常时向你提问 |
| L2 | 每项目/专职任务一个，有记忆 | 便宜模型或 aigw 聚合 | **日程秘书**：采集→分类→维护 SQLite→推钉钉 |
| L3 | 专能子 Agent + GUI 闭源软件执行体 | 尽量零 token（GUI/HID） | M1 无实例（M3 引入） |

**L1 成本纪律**：K3 输出 ¥100/M 且始终开启思考（推理 token 计入输出），因此 L1 **不参与**逐条消息分类与工具循环，只做统筹与对话。规划任务（M2）若成本偏高，可下放专职 L2「规划员」。

## 7. 决策记录（已拍板）

| # | 决策 | 结论 | ADR |
|---|------|------|-----|
| ① | 通知通道 | MVP 用钉钉机器人过渡；**Stream 模式双向**（推送 + 文本确认）；正式版为桌面原生通知 + 独立移动端 | 0002（修订） |
| ② | chatlog 常驻 | 开机自启（Startup 目录），依赖微信登录态 | 0003 |
| ③ | 钉钉接入 | 无开放 API，须第三方本地解密；M1 仅作通知出口 | 0004 |
| ④ | 增量识别 | 规则过滤（本地）+ 模型确认 | 0005 |
| ⑤ | 编排底座 | Hermes 不迁移；**MVP 明确不引入 LangGraph** | 0006（修订） |
| ⑥ | 日程状态层 | **SQLite** 结构化表；Mind 保持知识/画像真源 | 0007 |
| ⑦ | 看板 | 进 MVP；**Electron 桌面原生页面**；可手动增删改；轮询刷新 | 0008 |
| ⑧ | 变更语义 | 消息触发的日程变更标 **`pending`（待确认）**，钉钉一键确认后落定 | 0009 |
| ⑨ | 采集隐私 | **白名单**采集（只采点名的群/联系人）；结构上支持黑名单 | 0010 |
| ⑩ | Agent 分层 | L1/L2/L3 三级 + 角色→模型路由；L2 直读 Mind、写经无模型串行服务；Pico 用优先级队列（M3） | 0011 |

## 8. M1 验收标准

- [ ] chatlog 客户端落地：按白名单增量拉取 + Webhook 接收端接入调度（10 分钟巡检兜底）
- [ ] SQLite `events` 表落地，字段含 `source` / `evidence` / `prev_value` / `status`
- [ ] Electron 原生日程看板：显示当日+次日，支持手动增/改/删，10 秒内反映变更
- [ ] 消息触发的日程变更写入为 `pending` 并在看板显示新旧值对比
- [ ] 钉钉 Stream 机器人推送待确认项，用户文本回复 `确认 N` / `忽略 N` 可落定
- [ ] 时效性消息 15 分钟内完成"识别 → 入库 → 推送"
- [ ] Mind 窄切：读 `Vault/meta/Persona.md` 与项目状态；每日日程摘要写入 `Loom/`（经串行写入服务，不触发 verifier BLOCKER）
- [ ] 角色→模型路由配置存在：L1 与 L2 使用不同模型且可配置
- [ ] 连续 7 天统计改动率 ≤ 20%

## 9. 风险登记

| 风险 | 等级 | 缓解 |
|------|------|------|
| **隐私外泄**：全量微信消息送第三方云模型 | **高** | 白名单采集；规则过滤只在本地跑；仅命中的**单条消息片段**送模型（不送上下文全文）；支持会话黑名单（ADR-0010） |
| **L1 成本失控**：K3 输出 ¥100/M 且始终思考 | **高** | L1 不进工具循环、不做逐条分类；分类/抽取走便宜模型；监控月度 token 支出（ADR-0011） |
| 微信 ToS / 封号 | 高 | 仅本地读库解密，不注入不修改；轮询间隔 ≥ 30s |
| chatlog 版本升级破坏 API | 中 | 锁定 v0.5.2，API 层加版本适配 |
| 模型幻觉（日程判错） | 中 | `pending` + 人工确认语义（ADR-0009）；`evidence` 字段保留原始消息可回溯 |
| 微信退出登录导致采集中断 | 中 | 健康检查 `/api/v1/health`；连续失败推钉钉告警 |
| Mind 并发写冲突 / verifier BLOCKER | 中 | 写入统一经无模型串行服务：安全前缀校验 + 批量提交 + 提交前 verifier 预检 |
| 钉钉 Stream 依赖组织策略 | 低 | 通知层抽象，通道可切换 |

## 10. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V0.3 | 2026-08-24 | 范围收敛为 M1；成功标准改为可测量的"改动率 ≤ 20%"；新增 SQLite 状态层、Electron 原生看板、`pending` 确认语义、白名单采集、L1/L2/L3 分层与模型路由；巡检 30→10 分钟；明确 MVP 不引入 LangGraph；修正"chatlog 已落地"为"工具就绪、消费侧为零" |
| V0.2 | 2026-08-24 | 决策拍板，chatlog 常驻落地 |
*（内容由AI生成，仅供参考）*
