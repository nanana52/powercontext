# SUBMISSION — FlowMemo 比赛提交材料

## 项目信息

- **项目名称**：FlowMemo — 会记忆的周报工作台
- **赛题**：OceanBase × Qoder 2026 竞赛
- **分支**：`2026-competition-ecosystem`
- **开发主体**：Qoder CN Agent

## 交付清单

### 代码仓库
- **路径**：`qoder/flowmemo/`
- **分支**：`2026-competition-ecosystem`
- **Commit SHA**：源码快照 `b976c3ad95ea93e870c48f3966e06a29a486d7ba`；其后的证据、文档与 Function 修复各自成提交，最新 HEAD 用 `git log --oneline -5` 查看（提交哈希无法写进它所描述的仓库内容里）
- 发布产物：`dist/`（前端）与 `functions/`（Qoder Sites Server Function）
- 早期 Python 原型保留在 `server/`、`static/`、`run.py`，**未部署**，仅作演进留档

### 公开站点
- **URL**：<https://flowmemo-workspace-7u2qbfllad4.qoder.zone/>
- **访问权限**：公开（`access_mode: public`，`lifecycle: active`）
- **Qoder Sites 标识**：`projectId 01a19d11-54b8-795c-8dd2-7c804f35ed36` / `siteId 01a19d11-54bc-730a-89cc-890ac25e80c6`
- 最新已发布草稿：`actionId d7423740-f00e-4539-8d26-04d0afb4fb13`（`publishOperationId 01a1a01c-3155-7022-b555-13d86d304ad7`，前端产物与源码逐字节一致：线上 `js/app.js?v=20261103-6` 与 `dist/js/app.js` SHA-256 相同）
- 线上产物已与源码逐字节核对，见 `docs/EVIDENCE.md` 第 1 节

### PowerContext 集成
- 服务端真实调用（Server Function 代理，Token 只留在服务端环境）：
  - `GET /health/ready` — 健康检查（失败时线上 `/health` 会回显真实上游状态码与转发端口，便于区分"实例停机"与"端口错配"）
  - `POST /v1/scopes` — 为每位访客真实创建 Scope（`scp_…`）
  - `POST /v1/memory/remember` — 写入偏好，返回 `{changed, records}`
  - `POST /v1/context/prepare` — 赛题要求的读回链路，返回 `{status, content}`
  - `POST /v1/memory/search` — 结构化召回，返回 `{mode, hits}`
  - `POST /v1/memory/entries/list` — Scope 全量清点，用于 FTS 未命中时兜底
- 访客与 Scope 绑定关系保存在 HMAC-SHA256 签名 session token 中（30 天有效），因此**刷新页面与 Function 冷启动都不丢关联**
- 前端「核验证据」抽屉与「诊断日志」区展示脱敏记录（HTTP 状态码、命中数、`request_id`）
- 历史真实成功日志（2026-11-02）已归档在 `docs/EVIDENCE.md` 第 3.1 节

### 运行说明

线上站点直接访问即可，无需本地环境。

```bash
# 本地预览静态前端（记忆功能需线上 Server Function，本地会显示真实错误）
cd qoder/flowmemo/dist
python -m http.server 8901

# 可复现验收（纯标准库，无 mock）
cd qoder/flowmemo
python qa/live_acceptance.py                 # 打线上 Function 的记忆契约
python qa/powercontext_smoke.py --url "$POWERCONTEXT_URL"   # 直连 PowerContext
python qa/js_balance_check.py dist/js/app.js # 源码结构与编码检查
```

### Qoder UID
`01a19ccf-e5f1-7839-b26d-949579242087`

## 当前状态与未验证项

**8 项功能全部线上实测 PASS，无 BLOCKED 项（2026-11-03 06:33–06:45 UTC）。**

- `python qa/live_acceptance.py --output evidence/live.json` → **退出码 0，13/13 PASS**（真实 Scope 创建、真实写入、跨刷新召回、最新偏好覆盖、两访客 Scope 隔离、跨项目 token 重放被拒、外部 `scope_id` 被忽略、伪造/篡改签名 401、匿名 `/debug/memory` 404）
- 浏览器实测：健康状态显示"已连接"、保存需等 PowerContext 回执才清空文本框、刷新后召回真实回填并提示「已从 PowerContext 召回偏好」、周报章节顺序随偏好翻转（`已完成→风险→…` ↔ `风险→已完成→…`）、独立访客读不到他人偏好
- 逐条 HTTP 状态码、PowerContext `request_id` 与脱敏记录见 `docs/EVIDENCE.md` 第 2、3 节与 `evidence/live.json`

已核实的一个诚实性事实：中文偏好的召回命中来自 `entries/list` 全量清点兜底（`source:"entries"`），FTS 中文查询本身命中不足；功能结果真实，但召回路径不应描述为纯 FTS 命中。

**剩余非代码事项**（需你本人处理，我不代做）：

1. 推送比赛仓库：本机无该仓库远端配置、无 `gh` CLI，需你提供仓库地址并授权；
2. `docs/SUBMISSION.md` 的 **Qoder UID** 仍需你填写；
3. 线上 `POWERCONTEXT_URL` 目前实际生效的是 Codespaces 隧道地址（`upstream_host_sha256 = 069e2c2c`），它随实例闲置失效、且端口 Visibility 必须为 Public 才能被 Server Function 访问。若评审需要在任意时刻复现，建议换成稳定公开 HTTPS 托管；换地址后**必须**用新 `actionId` 重新 `prepare_site` + `publish_site`，仅改 Secret 不会刷新 Function 的环境变量。

## 验证命令

```bash
python qa/test_fixture.py
python qa/live_acceptance.py
python qa/powercontext_smoke.py --url $POWERCONTEXT_URL
python qa/submission_gate.py            # 仅本地材料检查
python qa/submission_gate.py --live     # 额外核对线上产物与源码逐字节一致
```

`live_acceptance.py` 退出码：`0` 全部可执行用例通过；`1` 存在 FAIL；`2` PowerContext 未就绪导致记忆用例未执行。

## 打包与仓库同步状态

- 交付包：`flowmemo-submission.zip`（42 个条目）；已排除 `data/`、`__pycache__`、描述符备份、包自身与包外校验和；本轮**已把 `evidence/live.json` 纳入包内**（其中 Scope 前缀已脱敏、不含 sessionId 与 Token），重建命令见 `docs/RUNBOOK.md`
  - **权威校验和只写在包外的 `flowmemo-submission.zip.sha256`**（`python qa/build_package.py` 每次重建都会刷新它）。本文档刻意不内嵌那段 64 位摘要：把摘要写进被摘要描述的包内会形成自指——最后一次文档修改又会让它过期。核对时以包外文件为准。
  - 修正记录：`qa/build_package.py` 旧版会把上一轮的 `.sha256` 一起打进新包（条目数 43），那是一份描述已不存在产物的过期证据；现已同时排除包体与校验和旁路文件。
- 本地 Git 仓库已初始化在分支 `2026-competition-ecosystem`，源码提交 `b976c3ad95ea93e870c48f3966e06a29a486d7ba`
- **尚未推送**：本机未配置该仓库的远端，也未安装 `gh` CLI；推送需你提供比赛仓库地址并授权
