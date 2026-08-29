# Vaelis 工程技术能力提升 & 代码质量把控方案

> 作者:资深开发工程师 | 日期:2026-07-16 | 基于仓库实测审计(非印象)

## 一、现状审计(证据)

| 维度 | 现状 | 评价 |
|---|---|---|
| 前端静态检查 (apps/desktop) | `eslint.config.mjs`(@typescript-eslint / perfectionist / react-hooks / unused-imports)+ `.prettierrc` | ✅ 配置完整 |
| 前端类型检查 | `typecheck`: tsc 双配置 `--noEmit` | ✅ 有 |
| 前端单测 | vitest + ~30 个 `node --test` 文件 | ✅ 扎实 |
| 前端依赖安全 | 根 `audit:*` 漏洞扫描 | ✅ 有 |
| **Python 静态检查 (aigw)** | `pyproject.toml` **无任何 ruff/mypy/black 配置** | ❌ 零 |
| **Python 类型检查** | 无 | ❌ 零 |
| **Python 单测** | 仅 `tests/test_antigravity.py` 等 3 个文件,无 pytest 接入脚本 | ⚠️ 薄弱 |
| **pre-commit 钩子** | 全仓库**无**(无 husky/lefthook/pre-commit) | ❌ 零 |
| **CI 质量门禁** | 仅 `release-desktop.yml`(构建发版),**PR 不跑 lint/typecheck/test** | ❌ 无 |
| **统一编码标准** | 无 `.editorconfig`,无跨项目共享配置 | ❌ 无 |

### 近期真实缺陷佐证"缺把关"
- **硬编码公共 OAuth secret 默认空串** → token exchange 返回 400(刚修复)。如有权限/类型约束或单测断言请求体形状,本可拦下。
- `resolveAigwDir` 路径解析脆弱,需靠 walk-up 补丁兜底;单实例锁逻辑导致应用静默退出——这类"能跑但不稳"的代码正是无人 review 的典型产物。

## 二、提升方案(四层结构)

### Layer 1 — 标准基线(低门槛、全员受益)
1. 根目录加 `.editorconfig`(换行/缩进/编码/尾随空格统一)
2. aigw `pyproject.toml` 补齐 `[tool.ruff]` + `[tool.mypy]` + `[tool.pytest.ini_options]`,确立 Python 侧 lint/类型/测试基线
3. 整理一份《工程标准》文档(命名、错误处理、秘钥管理、PR 规范)

### Layer 2 — 自动化门禁(让质量不靠自觉)
4. **pre-commit**:前端 eslint --fix + prettier;Python ruff + mypy;加 `detect-secrets`/gitleaks 防秘钥误提交
5. **CI 质量门禁(新增 `quality.yml`)**:PR/push 时双栈跑 lint + typecheck + test,失败**阻断合并**

### Layer 3 — 评审与带教(人的层面)
6. 引入 PR 模板 + 评审清单(至少 1 名资深 approve 才能合)
7. 我作为资深评审员,对现有脆弱代码做一轮 Code Review,并把 `resolveAigwDir`、单实例锁等作为**重构示范**(边改边讲,带教)
8. 秘钥/配置一律走 env + 文档,严禁硬编码

### Layer 4 — 知识沉淀
9. 把踩过的坑(单实例锁、token 交换、aigw 接线)沉淀为团队 wiki / runbook
10. 每周一个"代码质量小课"(从真实 PR 里挑正反例)

## 三、首期落地建议(需你拍板优先级)

不主张一股脑全上。建议先打"最痛且风险最高"的两块:
- **aigw Python 质量底座**(ruff+mypy+pytest 接入)—— 它最薄弱且已出过线上 bug
- **pre-commit + CI 门禁** —— 一次投入,长期受益,把前端已有的好工具真正"卡"住

具体从哪块起,见下方选择。
