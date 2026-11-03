# Qoder × OceanBase 参赛提交材料模板

> ⚠️ 这是空模板，不是已提测结果。请由 Qoder 在通过验收后复制并填写为 `docs/SUBMISSION.md`。

**项目名称**：FlowMemo｜会记忆的周报工作台

**核心问题**：把碎片化纪要转为可追溯的待办与周报；使用 PowerContext 跨会话复用写作偏好和项目决策。

**网站网址（Qoder Sites）**：`<由真实发布结果填写>`

**可见范围验证**：`<无痕窗口访问成功截图文件>`

**代码仓库 URL**：`<比赛指定私有仓库可供评审访问的地址>`

**代码分支**：`2026-competition-ecosystem`

**Commit SHA-1（完整 40 位）**：`<完整哈希>`

**Qoder 账号 UID**：`<用户从设置页面获取>`

**主要功能**：笔记导入；识别待办/决策/风险；可编辑任务；周报生成与导出；经用户授权保存 PowerContext 偏好；刷新后准备上下文并应用偏好。

**指定技术真实性证明**：

- 组件：PowerContext Server 版本 `<Qoder 按实际安装填写>`；部署地址（脱敏）`<填写>`。
- 业务链路：`/v1/memory/remember` 实际存偏好 → `/v1/context/prepare` 真实召回 → 生成周报时采用记忆偏好。
- 验收记录：`<真实命令输出和证据截图，不能贴 Token>`。

**运行说明**：`docs/RUNBOOK.md`

**验证样例**：`docs/DEMO_STEPS.md` + `fixtures/demo_notes.json`

**Qoder 开发记录**：`docs/QODER_DEV_LOG.md` + `docs/evidence/` 截图

**真实使用效果**：`<如无数据请写“暂无独立真实用户数据”>`

**限制与不支持**：`<按 Qoder 完成情况如实填写>`
