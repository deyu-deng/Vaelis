# Vaelis 已实现功能清单（当前真实代码，2026-07-13 核对）

> **重要：项目已重构。** 此前基于 `backend/`+`src-tauri/`+`aigw/` 的清单（2026-07-11 写于本文件）**已失效**——那套代码现整体归档在 `backup/`（旧 Vaelis / "Plobi" 形态）。
>
> 当前根目录是 **Hermes Agent（Nous Research）的上游 fork / 超集**，正在做 Hermes→Vaelis 去品牌化（见 `VAELIS_PATCHES.md`）。分支 `vaelis-dev`，基于上游 tag `hermes-upstream` = commit `4281151`。本清单基于**当前根目录真实代码**逐模块核对（3 路并行探查 + 关键入口验证），非只看 README/AGENTS.md。
>
> 标注：✅ 真实实现（含 file:line）／⚠️ 已实现但为实验性 / 用户触发 / 营销夸大／❌ 声称但代码缺失。

---

## 0. 架构总览
- Python agent core（`agent/` ~100+ 模块，核心 `conversation_loop.py` ~305KB）
- Messaging gateway（`gateway/`，含 `platforms/` 内置 + `plugins/platforms/` 插件）
- CLI（`hermes_cli/`，~60 命令组；入口 `cli.py` 748KB）
- 桌面（`apps/desktop/` Electron）、TUI（`ui-tui/` Ink/React）
- 工具集（`tools/` 70+ 模块）、插件（`plugins/` 平台/浏览器/图像/记忆/MCP）
- 调度（`cron/`）、MCP server（`mcp_serve.py`）

---

## 1. 多模型 Provider ✅
真实适配器，按 `agent.api_mode` 路由：
- Anthropic（`anthropic_adapter.py:735/832`）、Bedrock（`bedrock_adapter.py:1017/1059`）、Gemini 原生（`gemini_native_adapter.py:35/422`，含 OpenAI↔Gemini 翻译）、Codex/OpenAI Responses（`codex_responses_adapter.py:313`）、Azure OpenAI（`azure_identity_adapter.py:190`）、Vertex AI（`vertex_adapter.py:202`）、LM Studio（`lmstudio_reasoning.py:24`）、OpenAI/OpenRouter/xAI/DeepSeek/Nous/Qwen/自定义 base_url 路径。
- 证据：`conversation_loop.py:1421/1631/1852/1963`（anthropic/bedrock/chat_completions 分发）。

## 2. 持久记忆 ✅
- 内置文件型：`MEMORY.md`/`USER.md`，`§` 分隔符（`memory_tool.py:59`），重启重载 → **跨会话召回真有效**。
- `MemoryManager`（`memory_manager.py:495` prefetch / `:558` sync）。
- 外部 provider 插件：honcho、mem0、hindsight、**holographic（真实 SQLite+FTS5 混合检索 `plugins/memory/holographic/store.py:48-49`）** 等。
- 会话历史 SQLite+FTS5（`hermes_state.py:22/170`）。

## 3. 学习循环 / 技能 ⚠️（营销夸大）
- `/learn` 触发 Agent **现场**用 `skill_manage` 写 `SKILL.md`（`learn_prompt.py:99/143`）——**用户触发，无自主后台蒸馏引擎**。
- `learning_graph.py:254` 仅**可视化**；`learning_mutations.py:124/157` 仅用户编辑/删除。
- 技能系统本身真实现（`skill_manager_tool.py`、`skills_hub.py` 158KB）。
- ⚠️ README 称 "closed learning loop / autonomous skill creation" 与代码不符。

## 4. 上下文压缩 ✅
真实 LLM 摘要（`auxiliary_client` 真实网络调用），失败回退丢中间轮：`context_compressor.py:589/1958`、`conversation_compression.py:435/741`。

## 5. 浏览器 / Computer Use ✅
- 云端浏览器插件：browser-use、browserbase、firecrawl（真实网络驱动，`plugins/browser/browser_use/provider.py:188/209`）。
- 本地：tools 含 `browser_cdp_tool.py`、`computer_use_tool.py` 等。

## 6. 图像生成 ✅
OpenAI（`gpt-image-2` 文生图+编辑，`plugins/image_gen/openai:164/273/298`）、FAL（18 模型）、krea、openrouter、xai。真实 API。

## 7. MOA / 子代理委派 ✅
- `moa_loop.py:336/362` 真实并行 fan-out（`ThreadPoolExecutor`）+ aggregator。
- `tools/delegate_tool.py`（155KB）真实子代理委派。

## 8. 凭证池 / 用量计费 ✅（计费依赖外部 Nous Portal）
- `credential_pool.py:508` 多源（env/oauth/device_code/各 CLI 等）+ 写回 `auth.json`；`credential_persistence.py:151` 脱敏（仅存 SHA-256 指纹）。
- `credits_tracker.py:390` 解析响应头；`billing_view.py:199` 拉取 Nous 后端，**不可达时优雅降级**。

## 9. LSP / 代码智能 ✅
`agent/lsp/` 完整 LSP 客户端（client/manager/protocol/servers/workspace）。

## 10. 消息平台网关 ✅（全部实现，注意位置）
- **内置** `gateway/platforms/`：微信 `weixin`、QQbot `qqbot`、元宝 `yuanbao`、Signal `signal`、WhatsApp Cloud `whatsapp_cloud`、BlueBubbles、api_server、webhook、MS Graph webhook。
- **插件** `plugins/platforms/`：Telegram(412KB)、Discord(383KB)、Slack(195KB)、Email、Home Assistant、Matrix、Mattermost、IRC、SMS、Teams、Feishu、WeCom、DingTalk、Line、Google Chat、ntfy、Simplex、Photon、Raft 等。
- 全部经 `platform_registry` 自注册；`gateway/run.py:8665/8688` 先查 registry 再回退内置。
- ⚠️ 西方平台在 `plugins/`，不在 `gateway/platforms/`——README 的"Telegram/Discord/Slack"均真实现，只是位置不同。

## 11. Relay 跨平台连接器 ⚠️ EXPERIMENTAL
真实 WebSocket 连接器（`gateway/relay/adapter.py:46`、`ws_transport.py:204`），但包文档标注实验性、API 不稳、需 `GATEWAY_RELAY_URL` 开启（`relay/__init__.py:1-17`）。

## 12. Slash 命令 ✅
`GatewaySlashCommandsMixin`（`slash_commands.py` 223KB）+ CLI 侧 ~50 handler（`cli_commands_mixin.py`），共享后端模块；`slash_access.py` 访问控制。

## 13. DM 配对 / 授权 ✅
分层授权：`pairing.py`（一次性码 + 审批 + 白名单同步）+ `authz_mixin.py:264`（`_is_user_authorized`：per-platform/env + 聊天级 + 全局 + 配对 store 联合），缓解间接提示注入。

## 14. Cron 调度 ✅（自然语言有限）
真实引擎：`cron/scheduler.py`(175KB) + `croniter` + 间隔/时长/ISO/cron 表达式 + 多平台投递（`_deliver_result`）。
⚠️ `parse_schedule`(`jobs.py:476`) 仅接受**结构化简写**（"every 30m"/"2h"/cron 表达式），**无开放英文 NL 解析**。

## 15. CLI 命令树 ✅（~60 命令组）
`main.py:12283` `_BUILTIN_SUBCOMMANDS` 列出 ~60 组；`hermes_cli/subcommands/` 45+ argparse 模块（model/config/gateway/setup/cron/curator/skills/mcp/memory/doctor/update/kanban/claw/blueprint/dashboard 等）。

## 16. Electron 桌面 ✅（构建级验证）
多窗口、vaelis:// deep link、自定义 git 自更新（非 electron-updater）、~100 IPC 通道、内嵌终端(xterm+node-pty)、通知/剪贴板/FS/Git、云端+网关管理、bootstrap 安装流。
- ❌ **无系统托盘**：仅有透明 pet overlay 装饰窗（`main.ts:7148` setAlwaysOnTop），无 `new Tray`。
- ⚠️ 仅**构建/类型检查/单测**验证（dist 产物 + 30+ 主进程测试）；GUI 运行时（headless 无法实跑）。
- ⚠️ 第三方 UI kit `@nous-research/ui` 仍硬编码 "Hermes Agent" 标记（KNOWN GAP #1，运行可见）。

## 17. TUI（Ink/React）✅
真实交互终端 UI：多行编辑、slash 补全、输入/消息历史、overlays(hotkeys/mouse)（`ui-tui/src/entry.tsx`、`textInput.tsx`）。
⚠️ `hermes_cli/curses_ui.py` 仅是清单多选组件，**非聊天 TUI**。

## 18. 工具集 ✅（70+ 真实，无桩）
terminal/file/web/browser/computer-use/memory/skills/delegate/kanban/cron/messaging/媒体生成/TTS/转录/vision/MCP/审批安全/Microsoft Graph 等（`tools/`）。全仓 `NotImplementedError`/`# stub` 搜索仅命中抽象基类预期方法，无占位工具。

## 19. 终端后端 ✅（6 个全实现）
`tools/environments/` 下 Local(`local.py:930`)、Docker(`docker.py:568`)、SSH(`ssh.py:36`)、Singularity/Apptainer(`singularity.py:158`)、Modal(+managed `modal.py:164`)、Daytona(`daytona.py:30`)，均 `BaseEnvironment` 子类真实调用。

## 20. MCP ✅（client + server）
- Server：`mcp_serve.py`(35KB) FastMCP，10 工具（`hermes mcp serve`）。
- Client：`tools/mcp_tool.py`(245KB) 多传输 stdio/sse/streamable-http + OAuth + stdio watchdog。

## 21. aigw（AI 网关）🟡 部分完成
- **实现位置**：`aigw/`（FastAPI OpenAI 兼容网关：`/v1/chat/completions`、`/v1/models`、`/v1/embeddings`、`/healthz`）。
- **安全默认**：`profiles/safe.yaml` — 仅 mock + spawn-CLI；reverse（Cursor / Antigravity HTTP）默认关。
- **能力声明**：`/v1/models` 与 `/healthz` 暴露 `capabilities`（stream/tools/…/compliance）与 `version`。
- **桌面**：`apps/desktop/electron/main.ts` 的 `vaelisGateway` 可 spawn/stop/status；Windows 解析 `.venv\Scripts\python.exe`；无 `config.yaml` 时回退 `profiles/safe.yaml`。
- **缺口（诚实）**：agent 主路径未必默认把 `OPENAI_BASE_URL` 指到 aigw；CLI 仍无 sessionful/tools；Cursor chat 协议未闭环；reverse 仅研究档。

## 22. 国际化
`locales/` 16 个 yaml（中/西/乌尔都等）。未专项验证切换器接线（参照旧项目经验，需警惕"字典齐但无切换 UI"）。

## 23. North Star（人只审核与提想法）🟠 仅脚手架，未接业务
- **契约真源**：`docs/vaelis/north_star/GRILL_FREEZE.md`（2026-08-09 冻结，2026-08-24 修订）。
- **深模块**：对模型只暴露 **一个** tool `vaelis`（area+action）；HTTP 面 `/api/plugins/vaelis-north-star/*`；`lib/*` 不对外。
- **Plugin**：`plugins/vaelis-north-star/` + `dashboard/plugin_api.py`；测试 `tests/plugins/test_vaelis_north_star.py`。
- **缺口（诚实核对，2026-08-24）**：
  - **未默认启用**：standalone 插件需写入 `plugins.enabled`，目前只有 `docs/vaelis/profiles/master/config.yaml` 模板里有。
  - **HID 全是 mock**：`lib/hid/adapters/marvis.py` 的热键是 placeholder；Pico 固件未刷；`ScreenLock` 只是忙等互斥锁，尚无 ADR-0011 要求的优先级队列。
  - **`night.py` 不执行工作**：只 claim 任务，不驱动执行。
  - **`master.py::master_dispatch_plan` 无副作用**：返回建议步骤名，没有日程/冲突逻辑。
  - **`lib/vaelis-api.ts` 偏离桌面房规**：桌面端应走 `window.hermesDesktop.api({ path })`（见 `apps/desktop/src/hermes.ts`），该文件用裸 `fetch`，需在实现 `specs/agenda-board.md` 时收敛。
  - Skill 草稿仍须人批；手机通道复用既有 gateway。

## 24. MVP AI 秘书（里程碑 M1）🟡 采集→看板→通知→确认 已打通
- **真源**：`docs/specs/MVP-AI-Secretary-Requirements.md` V0.3 + `docs/specs/agenda-board.md`；运维见 `docs/runbooks/agenda-collector-setup.md`。
- **状态层**：`vaelis/agenda/`（`store` SQLite / `rules` 本地过滤 / `service` 待确认语义 / `router` REST）。`store` 与 `rules` **不含任何模型调用**（有测试守住）。
- **采集层**：`vaelis/collectors/chatlog/`（白名单 `config` / HTTP `client` / 中文时间解析 `timeparse` / 启发式 `confirm` / 去重 `state` / 编排 `pipeline` / `webhook`）。常见句式**无需模型**即可解析。
- **通知与确认**：`vaelis/notify/`（钉钉机器人，支持加签）+ `vaelis/agenda/dispatch.py`（短序号协议）+ 插件 `plugins/vaelis-agenda/`（`pre_gateway_dispatch` 拦截「确认 N」，**不唤醒模型**）。
- **桌面看板**：`apps/desktop/src/app/agenda/`，走 `hermes.ts` 的 `window.hermesDesktop.api`；复用 `Panel*` 与设计 token；四语言齐全；状态栏显示待确认数。
- **路由**：核心 `/api/agenda/*` 与 `/api/chatlog/*`（挂载在 `hermes_cli/web_server.py`，不依赖插件开关）。
- **测试**：`tests/vaelis/`（130 项，含隐私边界、去重、回滚、过期序号）+ `tests/plugins/test_vaelis_agenda_plugin.py` + `apps/desktop/src/store/agenda.test.ts`。
- **Mind 接入**：`vaelis/mind/`（`paths` 安全前缀 / `lock` 跨进程写锁 / `writer` 无模型串行写入 + verifier 预检 / `reader` 窄切读画像与项目）。`vaelis/agenda/mind_sync.py` 每日摘要落 `Loom/raw/chat-logs/digested/<date>/agenda.md`。旧的写死盘符已改为统一 `MIND_ROOT` 解析。
- **模型路由**：`vaelis/routing/`（角色→模型；把 ADR-0011 变成断言：L1 不得指向 GUI-only 表面、L2 不得与 L1 同模型）。默认 L1=`moonshot/kimi-k3`，L2=`deepseek/deepseek-chat`。
- **缺口（诚实）**：
  - 模型确认器尚未接入——只说时间不说日期的消息记为 `unresolved`，需人工补。
  - Mind 写入默认 `commit=False`（只落盘不提交 git），需手动或后续切片接自动提交。
  - `plugins/memory/mind/` 这个 MemoryProvider 仍是空壳；M1 走的是 `vaelis/mind/` 窄切，不接管 agent 每轮记忆（F1 决策）。
  - 模型路由目前只是**配置与校验**，尚未被真实调用点消费。
  - 未在真实 chatlog/钉钉环境端到端实跑（全部为单测 + 假客户端）。
- **LangGraph**：零依赖零 import，MVP 明确不引入（ADR-0006 修订）。

---

## 与营销/文档的 GAP（"存在 ≠ 能用"重点）
1. **学习循环**：README 宣称"自主技能创建/闭环学习" → 实际是 `/learn` 用户触发 + 可视化；North Star 增加了**被动观察→Skill 草稿（须人批）**骨架，仍非全自动入库。
2. **Electron 托盘**：代码**无系统托盘**（pet overlay 替代）。
3. **Relay**：实验性、未稳定、需手动开启。
4. **Cron 自然语言**：仅结构化简写，非开放 NL。
5. **桌面 GUI**：仅构建/类型/单测验证，headless 未实跑；第三方 UI kit 仍显 "Hermes Agent"。
6. **aigw**：网关本体在 `aigw/` 可启动；桌面 IPC 已接 spawn，但 **Hermes agent 默认路由 / 一键 onboarding 闭环仍未完成**。
7. **计费/用量**：真实客户端逻辑，但依赖外部 Nous Portal，不可达时降级。

## 与上一版清单的关系
- 上一版（2026-07-11）针对 `backend/`+`src-tauri/`+`aigw/` 的 Plobi 形态 → **现已归档至 `backup/`，全部结论失效**。
- 当前根目录为 Hermes fork，功能面远超旧版（多平台网关、多模型、MOA、LSP、6 终端后端、MCP、70+ 工具等）。
