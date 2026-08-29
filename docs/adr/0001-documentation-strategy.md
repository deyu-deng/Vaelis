# ADR-0001: Vaelis 文档体系采用 Diátaxis + ADR 策略

- **状态**：Accepted
- **日期**：2026-08-24
- **决策者**：Vaelis 文档整理（基于 GitHub 调研）

## 背景

Vaelis 项目文档此前散乱分布在 `Code\docs\` 与 `Docs\` 多个层级，AI 频繁新建文件，
导致"又乱又散"。需要一套可长期执行的文档组织策略，明确"最终形态（Vaelis 完整愿景）"
与"MVP 目标（短期验证性功能）"两条线的归属，并约束未来新增文档的纪律。

## 决策

1. **采用 Diátaxis 四象限组织文档**，在 `Code\docs\` 下建立结构化目录：
   - `adr/` — 架构决策记录（Architecture Decision Records）
   - `specs/` — 规格（Specifications，实现级）
   - `runbooks/` — 运维手册（操作步骤类）
   - `reference/` — 参考资料（契约、设计、组件说明等）
   - `audit/` — 审计与质量基线（验收、RCA、工程计划）
   - `templates/` — 文档模板（约束新增文档走模板）
2. **外部顶层目录 `Docs\`** 保留真源文档（MVP-AI-Secretary-Requirements.md、
   AI-Native-Life-System-Spec-V1.md），并新增 `Docs\archive\` 归档历史/过时文档。
3. **两条线归属**：
   - 最终形态 = `docs\vaelis\north_star\` 契约 + 顶层 Spec（AI-Native-Life-System-Spec-V1.md）
   - MVP 目标 = MVP-AI-Secretary-Requirements.md（真源）+ `docs\specs\` 实现级规格
4. **AGENTS.md 追加"文档纪律"小节**：新增文档必须走 `templates/` 模板；
   过时文档必须吸收后删除或归档；禁止只堆不清理。
5. **只动不删**：除明确列出的三份过时文档（AUDIT.md / BULEPRINT.md / CONTEXT.md，
   内容吸收至 `audit/legacy-audit-checklist.md` 与 `reference/legacy-glossary.md`）外，
   其余文档一律仅移动、不删除。

## 后果

- **积极**：文档按四象限归位，引用链通过 `specs/README.md` 固化；未来新增文档有明确落位与纪律。
- **代价**：历史文档路径变更，需要更新仓库内引用；归档目录 `Docs\archive\` 承载历史内容但不再作为活跃来源。
- **回滚**：所有移动均有 file-organizer 历史记录，可撤销还原。
