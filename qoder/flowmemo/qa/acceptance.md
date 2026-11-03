# 验收清单（Qoder 执行并保留真实输出）

## A. 基础功能（强制）

- [ ] `fixtures/demo_notes.json` 导入后有 2 笔原始记录、4 项待办、2 条决策、2 条风险。
- [ ] 每个待办能编辑/标记完成；数据刷新后仍保留（所选持久化方案必须真实）。
- [ ] 周报不编造完成事项；来源能对应 note-a / note-b。
- [ ] 周报可复制、下载 Markdown，手机宽度下不会溢出。
- [ ] 跨项目数据隔离，输入特殊字符不触发脚本执行。

## B. PowerContext 真接线（强制）

- [ ] 服务端 `GET /health/live` 真实访问成功（仅证明服务连接）。
- [ ] 用户点击「保存偏好」后，由后端真实 POST `/v1/memory/remember`，保存回执有 records（不接受假回执）。
- [ ] 浏览器刷新/新会话后，后端 POST `/v1/context/prepare` 返回 status `ready`、非空内容，包含相同偏好关键词。
- [ ] 生成周报时从真实回忆推导章节顺序，风险章节出现在已完成之前。
- [ ] 断开 PowerContext 后显示明确的“未连接/不可用”，不能显示伪造的成功状态。
- [ ] API Token 仅在后端，浏览器请求和构建包不含秘密；Scope ID 不被当作身份授权。

## C. Qoder + Qoder Sites（强制）

- [ ] Qoder 完成主要源码开发和调试；至少 3 张脱敏 Qoder 开发截图。
- [ ] Qoder Sites 公网站点真实发布，个人账号「任何人都可访问」。
- [ ] 用无痕窗口验证网站能访问并完成可用功能；有实际截图。
- [ ] 网站有项目简介、核心功能、演示及仓库链接。
- [ ] `docs/RUNBOOK.md`、`docs/DEMO_STEPS.md`、`docs/SUBMISSION.md` 和完整 Git commit 生成。
- [ ] 公网站点核心记忆功能若依赖独立后端，需要实际公网可达并可复现；否则标明未完成，不能以 mock 冒充。

## D. 可交付资料（强制）

- [ ] 公开站点 URL（无登录打开）
- [ ] 比赛指定仓库 URL、`2026-competition-ecosystem` 分支、40 位 SHA
- [ ] Qoder UID 和实际对话证据
- [ ] 一条可复现 PowerContext 记忆写入 + 读回记录（脱敏）
- [ ] 可从干净环境跟着 README 运行的步骤

**未经完整验收，不能在交付报告上写“全部完成 / 20 分已到手”。**
