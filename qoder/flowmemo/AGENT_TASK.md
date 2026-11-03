# 给 Qoder CN Agent 的唯一主任务

你是本作品的**实际主要开发者**，比赛要求项目主要功能由 Qoder 完成、使用 PowerContext 或 seekdb 真实提供核心能力，并使用 Qoder Sites 发布。你必须实际执行，不可只生成计划或 mock。

## 仓库边界

工作区 `/workspaces/powercontext`，要求在已有 `2026-competition-ecosystem` 分支工作。所有新增项目资产必须位于 `qoder/flowmemo/`。不要修改 `seekdb-core`，不要调用 Bazel，不要改根仓库的核心实现，不要覆盖其他竞赛目录。若在 Qoder 独立云工作区开发，先导入大赛指定仓库相同分支再动手。

## 你的交付任务（必须执行）

1. 阅读 `PROJECT_SPEC.md`、`fixtures/demo_notes.json`、`qa/acceptance.md` 与 PowerContext 官方 API Quick Start `https://powercontext.oceanbase.io/en/docs/develop/api-quickstart/`；检查本仓库的现有 qoder 目录和技术约束。
2. 由你**从零实现** FlowMemo 应用：前端、后端/Server Functions、数据模型、周报生成、任务编辑、页面自检。优先用 Qoder Sites 原生托管支持的栈，少依赖，干净布局。不要只生成宣传 landing page。
3. PowerContext 真实集成必须发生在用户「保存偏好」和「生成周报」业务链：服务端调用 `/v1/memory/remember` 写记忆，以及 `/v1/context/prepare` 读回，不能只有一个 ping，也不能用 localStorage/数据库假扮 PowerContext。认证凭据只出现在服务端 secret 环境变量。
4. PowerContext 服务端可以是独立可复现的 Python 服务；优先调查 Qoder Sites 环境是否能承载合规的 PowerContext 服务端。若不支持，提供可复现的 `compose.yaml` 或官方 uv 部署和一个能持续访问的外部部署途径，且站点 Server Functions 通过私密服务端地址访问；不得把本地 127.0.0.1 写成网站部署可访问的 URL。若当前无法获得公网服务，必须醒目标记“在线演示仅展示基础流程，PowerContext 联机回路待连接”，**不能虚报全功能通过**，并给出最少用户操作的真实发布选项。
5. 用 `qa/powercontext_smoke.py` 或等效测试验证独立的 PowerContext 记忆写入/召回。再用浏览器实际操作完整端到端链路：输入记录 → 待办抽取 → 编辑 → 保存偏好 → 刷新页面 → 生成周报 → 读取并使用记忆。记录两个网络操作真实成功的脱敏证据。
6. 由 Qoder 实际编写 README、运行说明、依赖锁定、演示与自动化测试、错误态说明、站点文案；执行 lint/build/tests，发现失败自行修复。
7. 使用 Qoder Sites 内置建站/Agent App/发布能力部署。在真实预览里验证，然后经用户授权发布，个人账号设置「任何人都可访问」。用无痕/退出登录窗口验证并存截图。提交记录中必须能核对 Qoder 负责编码、调试与发布。
8. 在 `docs/` 下填完 `RUNBOOK.md`、`DEMO_STEPS.md`、`EVIDENCE.md`、`SUBMISSION.md`、`QODER_DEV_LOG.md`。不要伪造 UID、网址、测试结果、用户数量或性能收益。
9. Git 提交本作品路径（只 add `qoder/flowmemo/`），推送到原赛题要求的**比赛私有仓库**同名 `2026-competition-ecosystem` 分支。推送前确认 remote，避免推错到 oceanbase 官方仓库。记录完整 40 位 commit hash。
10. 输出最终：站点公开 URL、代码 repo/branch/full SHA、个人 Qoder UID 获取指引、使用 PowerContext 的证据、当前未实现项（若有）。不要要求用户反复粘贴冗长日志。

## 必须实现的 UI

中文工作台，左侧会议记录输入/示例导入，中间结构化任务面板（负责人、截止日、状态、优先级），右侧可复制/下载的周报预览。上方四个 KPI（记录数、待办数、已完成数、风险数），项目选择、搜索筛选；「长期记忆」卡片明确区分 PowerContext 已连接/断开；「核验证据」抽屉展示不含秘钥的最近写入/召回结果及官方接口路径。移动端可用。复用方案须记录来源。

## 必须遵守的安全/真实性

- 默认只使用 fixtures 的虚构资料；公共演示页提示勿上传真实机密。
- 禁止在客户端持有 PowerContext Token，禁止硬编码真实账号信息。
- 每访客数据隔离（服务端可信 session/Scope 映射），不能把 Scope ID 当授权鉴权。
- 未连接 PowerContext 时明确报错/禁用记忆按钮；允许展示非记忆型演示流程，但不能标记“已完成技术结合”。
- 数据不存在时显示“暂无历史记忆”，不可凭空补出记忆。
- 绝不绕过 Sites 公开访问的用户确认，禁止把未经测试内容说成已发布。
- 本人（Qoder）必须做主要开发，不能把材料包当作已完成项目直接发布。

## 完成定义

满足 `qa/acceptance.md` 中全部强制项，再请用户确认提交比赛。不能满足时说明阻碍与可复现的修复路径，不停留在“任务已规划”。
