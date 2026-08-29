# Runbook：启用日程采集与钉钉确认

- **目标**：让微信白名单群里的日程变更在 15 分钟内进入看板并推到手机，且能一句话确认
- **适用环境**：Windows；chatlog v0.5.2（`127.0.0.1:5030`）；Vaelis `hermes serve` 后端
- **更新日期**：2026-08-24

## 前置条件

- [ ] 微信已登录，chatlog 已开机自启常驻（ADR-0003），`http://127.0.0.1:5030` 可访问
- [ ] Vaelis 后端可启动（桌面端会自动拉起 `hermes serve`）
- [ ] 钉钉自定义机器人已创建，拿到 Webhook URL；若开启了「加签」，同时拿到密钥
- [ ] 已确定要采集哪些群/联系人（**白名单**，ADR-0010：没列的一律不读）

## 执行步骤

1. **写采集白名单**，文件 `%USERPROFILE%\.hermes\vaelis\chatlog.json`：

   ```json
   {
     "enabled": true,
     "base_url": "http://127.0.0.1:5030",
     "talkers": ["班级群", "课题组", "张导师"],
     "poll_minutes": 10
   }
   ```

   - `talkers` 填 chatlog 里的会话名（群名或备注名）；**留空等于不采集任何内容**
   - 预期输出：文件存在且为 UTF-8 无 BOM

2. **配置钉钉通知**（环境变量，属密钥，不进 `config.yaml`）：

   ```powershell
   setx DINGTALK_WEBHOOK_URL "https://oapi.dingtalk.com/robot/send?access_token=..."
   setx DINGTALK_WEBHOOK_SECRET "SEC..."   # 仅当机器人开启了加签
   ```

   - 预期输出：新开的终端里 `echo $env:DINGTALK_WEBHOOK_URL` 有值

3. **启用确认拦截插件**，在 `%USERPROFILE%\.hermes\config.yaml`：

   ```yaml
   plugins:
     enabled:
       - vaelis-agenda
   ```

   - 作用：手机回复「确认 3」时直接落定，**不唤醒模型**（省 token，见 ADR-0011）

4. **重启后端**（或重启桌面端），确认路由已挂载。

5. **配置 chatlog Webhook** 指向：`http://127.0.0.1:<后端端口>/api/chatlog/webhook`

6. **挂上兜底巡检**（Webhook 会漏；10 分钟一次自洽 15 分钟 SLA）：

   ```
   hermes cron
   # 新建任务，每 10 分钟 POST /api/chatlog/sweep
   ```

## 验证

- `GET /api/chatlog/status` → `enabled: true`、`chatlog_reachable: true`、`talkers` 数量正确
- 在白名单群里发一句「明天下午三点开组会」，随后：
  - `GET /api/agenda/pending` 出现该条目，`status=pending`，`evidence.snippet` 只有片段
  - 桌面看板出现琥珀色「待确认」，状态栏显示待办数
  - 钉钉收到 `[Vaelis] 1. …` 并带「回复「确认 1」或「忽略 1」」
- 手机回复 `确认 1` → 钉钉回「已确认」，看板转为已确认
- 在**非白名单**会话里发同样的话 → 什么都不该发生（隐私边界生效）

## 回滚

- 停止采集：把 `chatlog.json` 的 `enabled` 改为 `false`，重启后端
- 停止通知：清空 `DINGTALK_WEBHOOK_URL`
- 停止确认拦截：从 `plugins.enabled` 移除 `vaelis-agenda`
- 清空已采集的日程：删除 `%USERPROFILE%\.hermes\vaelis\agenda.db`（**不可回滚**，手动录入的条目会一并丢失）
- 重置去重台账（会导致旧消息被重新识别一次）：删除 `chatlog_state.db`

## 备注

- 环境变量覆盖（测试用）：`VAELIS_CHATLOG_CONFIG`、`VAELIS_CHATLOG_TALKERS`、`VAELIS_CHATLOG_URL`、`VAELIS_AGENDA_DB`、`VAELIS_CHATLOG_STATE_DB`
- 常见问题：
  - 钉钉返回 `310000` → 机器人开了加签但没设 `DINGTALK_WEBHOOK_SECRET`，或安全设置里的关键词不匹配（消息以 `[Vaelis]` 开头，可把它设为关键词）
  - 看板一直空 → 先看 `/api/chatlog/status` 的 `chatlog_reachable`；为 false 通常是微信退出登录
  - 明明群里说了却没识别 → 规则要求**时间表达式 + 话题关键词**同时出现；只有时间或只有关键词会被过滤
  - 识别到但没排进日程 → 报告里的 `unresolved` 计数；多为「只说了几点没说哪天」，这类目前需要人工在看板补
- 序号 24 小时过期，过期后请在看板处理
*（内容由AI生成，仅供参考）*
