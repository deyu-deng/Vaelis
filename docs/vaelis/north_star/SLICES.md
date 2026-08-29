# 审核带宽切片 S0–S11

每一片 = 一次可审完的合并单元。AI 可在片内连写；**下一片默认等你批准**。

| 切片 | 验收 |
|---|---|
| S0 | Mind `plan.md` + 本目录契约存在且与北极星一致 |
| S1 | Master profile 模板 + `vaelis_master_*` 工具可派工/收摘要 |
| S2 | HID 设备模型 + mock/pico 桥「键鼠可达」API |
| S3 | `vaelis_hid_run` surface=marvis 端到端（可 mock） |
| S4 | `vaelis_route` 返回 Marvis→hid / Antigravity→aigw |
| S5 | 队列尊重 risk；night 只跑 L0/L1；早报钩子 |
| S6 | `vaelis_preview` + desktop preview-bus 优先级 |
| S7 | 示范域（code）四阶段门禁可暂停/批准 |
| S8 | `vaelis_mobile_*` + `/vaelis` slash 状态/批准 |
| S9 | butler skills：早报、digest、额度预警 |
| S10 | scout + passive-learn skills |
| S11 | self-upgrade + butler-extended + domain registry |

## 并行

工程上 S2 可与 S1 并行起草；**审核顺序**仍建议 S0→S1→S2→S3。
