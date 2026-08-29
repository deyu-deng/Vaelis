# Vaelis North Star

**人只负责审核和提想法；其余全交给系统。**

本目录是北极星契约。实现状态另见 `docs/IMPLEMENTED_FEATURES.md`。  
推进按**审核带宽切片**，不用传统人月。

## 文档（阅读顺序）

| 文件 | 内容 |
|---|---|
| **[GRILL_FREEZE.md](./GRILL_FREEZE.md)** | **需求真源（grill 冻结清单）** |
| [OSS_REUSE.md](./OSS_REUSE.md) | O3 复用调研模板与许可证白名单 |
| [RISK_AND_GATES.md](./RISK_AND_GATES.md) | L0/L1a/L1b/L2–L4、夜窗、K3、阶段门禁 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 执行脑 / 记忆脑(Mind) / 手 |
| [API.md](./API.md) | 公开接口（深模块边界） |
| [SLICES.md](./SLICES.md) | 历史切片备忘（实现排期仍按审核带宽） |

## 冻结摘要（2026-08-24 更新）

- 品牌独立；底座可换；复用全 GitHub（O3）。  
- **三级 Agent**：L1 最好模型（当前 Kimi K3）只统筹 / L2 便宜模型领域闭环 / L3 GUI 执行体零 token；W1 窄接口。  
- Mind：知识与画像真源（`MIND_ROOT` + 单 git remote）；**运行时状态归 SQLite**。L2 直读、写经无模型串行服务。  
- HID：H3 目标 + C1 验证码；1 机串行；Pico 用 **H2 优先级队列**。  
- 手机：钉钉 **Stream 双向**过渡 → 独立 Vaelis App；钉钉 V2 缩略预览。  
- 桌面：内置日程看板已进 MVP（Electron 原生）。  
- 示范域：代码 + 文档；其它类型留重领域包。  
- 赚钱：猎犬 → 人批（E3）。  

> 短期 MVP 目标不在本目录，见 `docs/specs/MVP-AI-Secretary-Requirements.md`。

## 代码入口（实现，非契约）

- Plugin: `plugins/vaelis-north-star/`  
- Mind adapter scaffold: `plugins/memory/mind/`  
- Master profile template: `docs/vaelis/profiles/master/config.yaml`  
- Skills: `skills/vaelis/`  
