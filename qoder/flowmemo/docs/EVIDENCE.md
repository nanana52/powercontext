# EVIDENCE — FlowMemo 开发与验证证据

> 本文件只记录**实际执行过**的结果。未执行的用例标为 `BLOCKED` 或 `未执行`，不标 PASS。
> 复现命令见 `qoder/flowmemo/README.md` 第 5 节与 `qa/live_acceptance.py`。

## 1. 线上发布产物一致性（2026-11-03，curl 直取，与浏览器缓存无关）

| 验收项 | 结果 | 证据 |
|--------|------|------|
| 站点未更换 | PASS | `prepare_site`/`publish_site` 全程返回同一 `siteId 01a19d11-54bc-…`，host 仍为 `flowmemo-workspace-7u2qbfllad4.qoder.zone` |
| 线上 HTML 含诊断区 | PASS | 2026-11-03 06:31 UTC `curl /index.html` → 命中 `diagnosticLog`；脚本引用为 `js/app.js?v=20261103-6` |
| 线上 app.js 为新版 | PASS | `curl /js/app.js?v=20261103-6` → HTTP 200、25741 字节，SHA-256 前缀 `f3101f836d81f1ff` 与本地 `dist/js/app.js` 逐字节相同 |
| 破缓存参数返回同一内容 | PASS | 带 `?v=` 与不带 `?v=` 在旧草稿下**同样返回 19786 字节旧文件**，证明旧问题是发布快照陈旧，不是浏览器缓存 |
| Server Function 已更新 | PASS | `GET /functions/v1/app/health` 返回新字段 `reachable` / `upstream_status`（旧版无此字段） |
| Function 路由面与 `functions/handler.ts` 一致 | PASS | 实调 `/functions/v1/app/debug/memory` → `404 not_found`（该端点确已从源码删除，不再匿名暴露记忆）；`POST /session/ensure` → `502 {"ok":false,"error":"powercontext_failed","upstream_status":404}`，说明请求真实穿透到 PowerContext，而非本地伪造 |
| Secrets 未被改动 | PASS | 草稿仅声明 Secret 名称 `POWERCONTEXT_URL`、`POWERCONTEXT_TOKEN`，未写入任何值；`SIGNING_SECRET` 从未配置，已在 `secretNames` 中剔除 |
| 外部依赖可定位 | PASS | `GET /functions/v1/app/health` → `{"upstream_port":"18080","upstream_status":404,"reachable":true}`：转发层活着但 18080 上无监听，据此判定为端口/进程问题而非站点缺陷 |
| 核验证据抽屉可展开 | PASS | 线上浏览器实测 `getComputedStyle(#evidenceContent).display` 为 `none → block → none`，标题箭头随开合在 `▸/▾` 间翻转（修复前恒为 `none`，抽屉永远打不开） |

**踩坑记录**：复用同一 `actionId` 调 `publish_site` 会重复部署 `prepare_site` 当时冻结的快照（描述符内固化了 `indexHtml` 与 `artifactSha256`），磁盘新文件永不生效。内容变更必须换新的 `actionId` 重新 `prepare_site`。

> 本仓库保留了一份**过期**的描述符文件 `qoder/flowmemo/.FlowMemo 周报工作台.qoder.site`（`actionId 01a19dd0-…`、`artifactSha256 a3b1f7eb…`）。它解出来的 `indexHtml` 没有诊断日志区、引用无版本号的 `js/app.js`，正是上面这个坑的物证，仅作留档。`prepare_site` 生成的描述符不可手工编辑，也不代表当前线上内容——当前线上以本表第 2–5 行的实测为准。

## 2. 前端功能 — 浏览器实测（2026-11-03，线上站点）

| # | 验收项 | 结果 | 实测证据 |
|---|--------|------|----------|
| 1 | 顶部状态不永久停在"检测中…" | PASS | 2026-11-03 06:34:32 UTC 起徽章渲染为"已连接"（上游不可达时渲染"未连接"并给出真实错误，两种状态都不停留在"检测中…"） |
| 2 | 健康检查显示"已连接" | **PASS**（2026-11-03 06:35 起） | 诊断行 `PowerContext health: ready (HTTP 200) type=application/json req=6c0a31ec611188b3`；页面文本「已连接 PowerContext」 |
| 3 | "载入演示"可用 | PASS | 点击后 `state.notes=2`、`state.tasks=4`、KPI 记录数=2、toast「已导入 2 条演示记录」 |
| 4 | 刷新后记录与待办仍在 | PASS | 点击「载入演示」后 notes=2 / tasks=4 / decisions=2 / risks=2、KPI 2/4/2/2；勾选「修复登录页 Bug」使其 `task-item done`、KPI 已完成 1→2；`location.reload()` 后仍为 notes=2 / tasks=4 / done=2 |
| 5 | 真实 Scope 保存偏好 | **PASS** | 06:35:21 `API 200 /memory/preference/save` → 诊断 `Memory saved in PowerContext; request=5651009969a3390e`，**成功回执到达后**文本框才清空；06:38:12 第二次保存 `request=1778b4faff710f2a` 同样先 200 后清空（失败路径保留输入的对照见本节末） |
| 6 | 刷新后从 PowerContext 召回 | **PASS** | 06:35:51 重新加载页面 → `Verified memory session`（同一 Scope 由签名 token 恢复）→ 06:36:28 `Memory recall: found, source=entries, count=3` → 文本框被真实回填 `周报先写已完成事项，再写风险，最后写下周计划`，toast「已从 PowerContext 召回偏好」 |
| 7 | 召回偏好真实影响章节顺序 | **PASS** | 偏好为「先写已完成…」时生成周报章节：`已完成 → 风险 → 下周计划 → 进行中/待办 → 决策`；把偏好改为「先写风险…」并保存（`request=1778b4faff710f2a`）后，06:38:43 召回 `count=5` → 章节翻转为 `风险 → 已完成 → 下周计划 → 进行中/待办 → 决策`；诊断行 `Memory-based report ordering applied` |
| 8 | 访客之间读不到彼此记忆 | **PASS** | 浏览器内走页面自身网络路径、不删任何本地数据（06:44 UTC，详见 §3.0 代码块）：两个独立访客 `qa_browser_a` → `scp_00n…`、`qa_browser_b` → `scp_3gy…`（Scope 不同）；A 保存 `req=553c63fd8050bb7b` 后 A 召回命中「浏览器访客A：先写决策」（`req=d6a9da1f44e51b6d`），B 召回 `preference:null`、`count:0`；用 A 的 token 以 B 的 projectId 重放 → `401 Invalid or expired session`、`leaked:false`。服务端另有 `visitor_isolation_scope_read` / `foreign_session_token_rejected` / `arbitrary_scope_id_ignored` / `anonymous_debug_endpoint_removed` 四项 PASS |

补充实测（同批浏览器会话）：
- 非法 `projectId` 被拒：`POST /session/ensure {projectId:"默认项目"}` → `400 {"ok":false,"error":"invalid_projectId"}`（项目名只作展示，Scope 键必须是 ASCII 标识）。
- 周报真实内容取自本地数据，无虚构完成项：`## 已完成` 仅列出被勾选的「完成 API 文档更新 @张三 2026-11-01」。
- 页面底部诊断日志逐条渲染时间、级别与脱敏信息（HTTP 状态码、`request_id`、命中数），不输出 Token 与完整 sessionId。
- 手动录入记录解析正确：新增「验收记录 C」含 `待办：/决定：/风险：` 三行 → notes 2→3、tasks 4→5、decisions 2→3、risks 2→3。
- 「下载 MD」真实触发 Blob：`type=text/markdown;charset=utf-8`、`size=711`。
- 「▸ 核验证据」抽屉开合实测 `display: none → block → none`，标题箭头随状态翻转。
- 章节排序函数实测（第 7 项的前端一半）：无偏好 → `风险|已完成|进行中/待办|决策|下周计划`；偏好「先写已完成…」 → `已完成` 排到 `风险` 之前；偏好「先写决策…」 → `决策` 首位。未提及的章节保留在尾部，不丢信息。

## 3. PowerContext 真实调用证据

### 3.0 端到端全绿（2026-11-03 06:33–06:45 UTC，本轮最终状态）

上游恢复连通后，`qa/live_acceptance.py` 与浏览器实测**全部通过**，无 BLOCKED 项：

| 层 | 命令 / 操作 | 真实结果 |
|----|-------------|----------|
| Function → PowerContext | `GET /functions/v1/app/health` | `upstream_status:200`、`upstream_content_type:"application/json"`、`upstream_json:true`、`health.status:"ready"`、`request_id:c3bbc658c1bce747` |
| 自动验收 | `python qa/live_acceptance.py --output evidence/live.json` | **退出码 0 = LIVE_ACCEPTANCE_PASS，13/13 PASS**（06:33:52 UTC） |
| 真实 Scope 创建 + 保存 | `/session/ensure` → `/memory/preference/save` | Scope `scp_1d…`，`request_id=5e942b96d8ac2eb5`，`saved:true` |
| 刷新后召回 | `/session/ensure`(带旧 token) → `/memory/preference/recall` | `verified:true`、`same_scope_id:true`、召回文本与保存值逐字相同，`count:2`、`source:"entries"`、`request_id=4a147ecb695b27c9` |
| 偏好改变周报章节顺序 | 保存反向偏好后再次召回 | `latest_preference_wins` PASS，`request_id=ffe6f381d1a2cdf2`；浏览器实测章节由 `已完成→风险→…` 翻转为 `风险→已完成→…` |
| 两访客记忆隔离 | 独立 Scope 读取 | 访客 B 得到不同 Scope（`scp_3z…` vs `scp_1d…`），召回 `preference:null`，未读到访客 A 的偏好 |

浏览器内的独立访客核验（走页面自身网络路径，**不清除任何本地数据**）：

```
POST /session/ensure {projectId:"qa_browser_a"} -> scp_00n…   (A)
POST /session/ensure {projectId:"qa_browser_b"} -> scp_3gy…   (B)   scopes differ = true
POST /memory/preference/save  A "浏览器访客A：先写决策" -> 200 saved:true  req=553c63fd8050bb7b
POST /memory/preference/recall A -> 200 pref="浏览器访客A：先写决策"        req=d6a9da1f44e51b6d
POST /memory/preference/recall B -> 200 pref=null count=0      ← 读不到 A 的记忆
POST /memory/preference/recall {projectId:B, sessionId:A的token} -> 401 leaked=false
```

### 3.0.1 Secret 换址的操作要点（本轮实测得出）

更新 `POWERCONTEXT_URL` 后线上仍打到旧 Codespaces 隧道（`upstream_served_by: tunnels-prod-rel-*`、`upstream_host_kind: github_codespaces_tunnel`）。原因是 **Function 的环境变量在发布时快照**：

- 复用旧 `actionId` 调 `publish_site` → 返回**完全相同的** `publishOperationId`，是幂等空操作，env 不刷新；
- 换新 `actionId` 走 `prepare_site`（等 `descriptorStatus:"written"`）→ `publish_site` → 新 `publishOperationId 01a1a01c-3155-…`，env 才生效，随后 `/health` 立即变为 `200 + application/json + ready`。

为此在 `/health` 增加了两个不泄露隐私的诊断字段：`upstream_host_kind`（`github_codespaces_tunnel` / `public_tunnel` / `loopback_or_ip` / `other_hosted`）与 `upstream_host_sha256`（主机名 SHA-256 前 8 位），用于确认运行时真正加载的是哪一条地址。

### 3.1 已达成过的真实成功记录（Function 日志，2026-11-02）

```
18:40:16  POST /v1/scopes          -> 201  request_id=405de86b9fa87ee0  scope_id=scp_4mthhdzzfmpsd7js4vtwpq284m
18:40:25  POST /v1/memory/remember -> 200  request_id=fbab95a58efb9940  keys=[changed, records]
18:40:34  POST /v1/memory/search   -> 200  request_id=65a531b8c1352fa0  keys=[mode, hits]
18:47:58  POST /v1/scopes          -> 201  request_id=5425417215f91b1b  scope_id=scp_4jt415cgd5nhnx4hrqzfpv1erf
18:49:34  POST /v1/memory/remember -> 200  request_id=af3a6974516f0308  keys=[changed, records]
18:51:54  GET  /health/ready       -> 200  request_id=aeb567d2deee0a36  keys=[status, checks]
18:53:10  POST /v1/memory/remember -> 200  request_id=8ae52619ecab2b89  keys=[changed, records]
18:54:04  GET  /health/ready       -> 200  request_id=bc33a5f6d2ea12c8
```

契约确认：`remember` 返回 `{changed, records}`；`search` 返回 `{mode, hits}`（**不是** `results`）；Scope 创建返回 `{scope_id, title, summary, parent_scope_id, context_references, external_references, version}`。

早期失败记录同样留档：`/v1/scopes` 使用 `{"name": ...}` 或自带 `access` 字段时返回 `422 invalid_access_request`，官方 payload 为 `{title, summary, idempotency_key}`。

### 3.2 历史状态（2026-11-03 06:00 前的取证，已被 §3.0 与 §3.5 取代）

```
GET /functions/v1/app/health
{"status":"ok","powercontext":{"configured":true,"reachable":true,"health":{"status":"unavailable"},"upstream_status":404}}
```

PowerContext 托管在 GitHub Codespaces 转发端口上，实例停止后对所有路径返回空体 404（`x-served-by: tunnels-prod-rel-*`，属 GitHub 转发层而非应用）。最后一次成功是 2026-11-02 18:54 UTC。这是外部服务停机，不是站点代码缺陷；站点侧行为是显示真实错误并保持基础功能可用。

**端口错配（2026-11-03 定位）**：`/health` 回显 `upstream_port: "18080"`，说明站点 Secret 指向 Codespaces 的 18080 转发端口；而 `deploy-powercontext.sh` 旧版硬编码 `--port 8000`。若按旧脚本重启实例，进程监听 8000、转发层 18080 无监听者，线上将继续 404。脚本已改为 `PORT="${PORT:-18080}"`，并在注释中写明该值必须与 `POWERCONTEXT_URL` 的转发端口一致。

**本次 404 的最终定论（2026-11-03 06:31 UTC 复核）**：端口号本来就一致，真正原因是转发端口的 **Visibility 为 Private**。私有端口对匿名客户端（Server Function、curl）在**所有路径**返回 `content-length: 0` 的空 404，响应头只有隧道层的 `x-served-by: tunnels-prod-rel-*`；用一个不存在的 codespace 主机名做对照探针，得到逐字节相同的响应，所以"私有端口"与"实例不存在"从站点侧不可区分，而登录态浏览器仍能访问 200。把 Ports → Visibility → Public 后 Function 侧立即拿到 HTTP 200 + `application/json`，见 §3.0 与 §3.5。

### 3.3 Codespace 重启后的复测（2026-11-03 06:03–06:12 UTC，匿名请求）

用户已在 Codespaces 内确认 `localhost:8000/health/ready` 与浏览器 HTTPS 均为 200 / `status=ready`。同一时刻从站点侧与本机**无 GitHub 会话 Cookie** 各发一次真实请求：

```
# 1) Qoder Sites Server Function（2026-11-03 06:03:14 UTC，x-request-id=29069e00-ed5d-4240-a21a-7ebec16ff565）
GET https://…/functions/v1/app/health
{"status":"ok","powercontext":{"configured":true,"reachable":true,"upstream_port":"18080",
 "health":{"status":"unavailable"},"upstream_status":404,"request_id":""}}

# Function 日志（同一小时，脱敏）
[FlowMemo PC] GET /health/ready  404   （request_id 为空）
[FlowMemo PC] POST /v1/scopes    404
[FlowMemo PC] upstream error Scope creation 404
[FlowMemo]    /session/ensure    502   PowerContext request failed
```

结论 1：Function 收到的是**空 body 的 404**，不是 PowerContext 的 JSON。`x-powercontext-request-id` 缺失（`request_id:""`）也印证响应根本没有到达应用层——2026-11-02 的成功调用每次都带回该头。

```
# 2) 本机 curl，无 Cookie，同一转发主机名（值已按端口脱敏，仅保留 Codespace 前缀）
GET https://savage-mausoleum-…-18080.app.github.dev/health/ready
HTTP/2 404 | content-length: 0 | 无 content-type
x-served-by: tunnels-prod-rel-jpe1-v3-cluster
vssaas-request-id: 48960cc9-39dc-4ad7-a73a-fc412f9d4ad0

GET https://savage-mausoleum-…-8000.app.github.dev/health/ready   -> 同样 HTTP/2 404，content-length: 0
GET https://bogus-mausoleum-…-18080.app.github.dev/health/ready   -> 同样 HTTP/2 404，content-length: 0（头完全一致）
```

结论 2：404 由 GitHub 转发层（`tunnels-prod-rel-*` / `vssaas-request-id`）返回，且**伪造的 Codespace 主机名得到逐字节相同的响应**。因此匿名请求无法区分"端口未公开"与"主机名失效"，但可以确定：**转发端口当前对未登录 GitHub 的客户端不可见**。浏览器能拿到 200 是因为携带了 GitHub 会话 Cookie；Server Function 与本机 curl 都没有该 Cookie。

结论 3（发布新版 Function 后由 Function 亲自证实，06:12 UTC）：`/health` 返回 `upstream_status: 404`、`upstream_content_type: ""`、`upstream_json: false`、`upstream_served_by: tunnels-prod-rel-jpe1-v3-cluster`、`body_prefix: ""` —— 上游实际是**零长度无 Content-Type 的 404**，既不是 JSON 也不是访问确认 HTML 页面。

**待用户处理（唯一人工步骤）**：在 Codespaces 的 **Ports** 面板把 PowerContext 实际监听端口的 **Visibility 由 Private 改为 Public**（若该端口未列出，按 `PORT=18080` 重新 `add port`），并回报浏览器地址栏里的完整 HTTPS 地址。之后由我核对：
- 若端口与现有 Secret 一致，直接复测 `/health` 应返回 `upstream_json: true`、`health.status: "ready"`；
- 若端口不同（例如 8000 而 Secret 是 18080），则 `POWERCONTEXT_URL` 必须更新，属"实际测试证明必须修改"的范围。

Codespaces 闲置自动关机 + 私有转发端口使这条链路无法被公开站点稳定调用；比赛提交若需可复现，建议改用公开 HTTPS 托管（详见 `docs/DEPLOYMENT_ARCHITECTURE.md`）。

### 3.4 本轮代码修复（已于 2026-11-03 06:12 UTC 发布，`actionId 114a8a92-0ea9-…`）

`functions/handler.ts` 的 `pcCall()` 不再用 `response.json().catch(() => ({}))` 静默吞掉非 JSON 响应，改为读取原始 body 并回报 `contentType` / `parsedJson` / `servedBy` / `bodyPrefix`：

- `GET /health` 新增 `upstream_content_type`、`upstream_json`、`upstream_served_by`、`body_prefix`，并把就绪判定改为 **JSON + 200 + `status=="ready"`**，隧道 HTML 一律记为 `non_json_response`；
- `requirePcOk()` 新增非 JSON 分支：2xx 但 body 不是 JSON 时抛出 `PowerContext returned a non-JSON body`，杜绝"代理页 200 被当成写入成功"；错误响应附带 `upstream_content_type`；
- 前端健康原因文案区分"不可达 / 非 JSON 响应（含 Content-Type）/ 上游 HTTP 码"，`dist/index.html` 脚本版本推进到 `js/app.js?v=20261103-6` 破缓存。

发布后由 Function 自己发起的真实结果（`python qa/live_acceptance.py --output evidence/live.json`，退出码 2 = BLOCKED）：

```
GET https://…/functions/v1/app/health
{"configured":true,"reachable":true,"upstream_port":"18080",
 "health":{"status":"non_json_response"},
 "upstream_status":404,
 "upstream_content_type":"",        ← 无 Content-Type，body 长度为 0
 "upstream_json":false,             ← 确认：不是 JSON，也不是 HTML 访问确认页
 "upstream_served_by":"tunnels-prod-rel-jpe1-v3-cluster",
 "request_id":""}
```

同轮 4 项不依赖上游的隔离用例仍全部 PASS（`forged_signature_rejected` 401、`tampered_token_rejected_on_save` 401、`renew_with_forged_token_rejected` 401、`anonymous_debug_endpoint_removed` 404）。第 5–8 项（真实 Scope 创建、保存、刷新召回、两访客隔离）**未执行**，标 BLOCKED，不标 PASS。

### 3.5 Secret 切换后的成功链路（2026-11-03 06:31–06:39 UTC，全部真实 HTTP）

用户更新 `POWERCONTEXT_URL` 后，`/health` 起初**仍**返回 Codespaces 的 `upstream_served_by: tunnels-prod-rel-*` —— 证明 Function 的环境变量在**部署时快照**，仅改 Secret 不生效。用新 `actionId` 重新 `prepare_site` + `publish_site`（同一 `siteId`，未新建站点）后，运行时才读到新值：

```
# 复用旧 actionId 再发一次 → 返回完全相同的 publishOperationId（01a1a00a-5ba0-…），env 未刷新
# 新 actionId d7423740-f00e-… → 新 publishOperationId 01a1a01c-3155-…，env 生效
GET /functions/v1/app/health
{"configured":true,"reachable":true,"upstream_host_kind":"github_codespaces_tunnel",
 "upstream_host_sha256":"069e2c2c","health":{"status":"ready"},
 "upstream_status":200,"upstream_content_type":"application/json","upstream_json":true,
 "request_id":"c3bbc658c1bce747"}
```

> `upstream_host_kind` / `upstream_host_sha256` 是本轮为定位"Secret 是否真的生效"新增的诊断：只回报主机名类别与 SHA-256 前 8 位，不外泄私有主机名。`069e2c2c` 与旧 Codespaces 主机名的摘要一致，说明**线上真正在用的仍是那条隧道地址**（现已可用），Cloudflare 隧道地址要么未写入 Secret、要么写入后尚未随新部署生效。

`python qa/live_acceptance.py --output evidence/live.json` 于 06:33:52 UTC 完整执行，**退出码 0 = LIVE_ACCEPTANCE_PASS，13/13 全部 PASS**：

| 用例 | 结果 | 真实证据（HTTP 状态 / PowerContext request_id） |
|------|------|------------------------------------------------|
| `health_check_responds` | PASS | 200，`upstream_status:200`，`application/json`，`req=530905582fcd3407` |
| `powercontext_ready` | PASS | `health.status:"ready"`、`upstream_json:true` |
| `preference_saved_to_powercontext` | PASS | 200，Scope `scp_1d…`，`req=5e942b96d8ac2eb5` |
| `scope_survives_refresh` | PASS | 200，`verified:true`，`same_scope_id:true` |
| `preference_recalled_from_powercontext` | PASS | 200，召回 `周报先写已完成事项，再写风险`，`source:"entries"`、`count:2`，`req=4a147ecb695b27c9` |
| `latest_preference_wins` | PASS | 200，召回翻转后的 `周报先写风险，再写已完成事项`，`req=ffe6f381d1a2cdf2` |
| `visitor_isolation_scope_read` | PASS | 200，另一访客 Scope `scp_3z…` 与访客 A 不同，`preference_returned:null` |
| `foreign_session_token_rejected` | PASS | 401 `Invalid or expired session`（A 的 token 拿到 B 的项目下被拒） |
| `arbitrary_scope_id_ignored` | PASS | 200，请求体里的 `scope_id` 被忽略，Scope 只取自签名 token |
| `forged_signature_rejected` | PASS | 401，`preference_leaked:false` |
| `tampered_token_rejected_on_save` | PASS | 401 |
| `renew_with_forged_token_rejected` | PASS | 401 |
| `anonymous_debug_endpoint_removed` | PASS | 404 `not_found` |

浏览器端 8 项功能实测见第 2 节（同一时段，`req=6c0a31ec611188b3` / `5651009969a3390e` / `1778b4faff710f2a` 等）。召回链路 `source:"entries"` 说明命中来自 Scope 全量清点兜底，FTS 中文查询命中数不足以定序 —— 该事实保留记录，不粉饰为 FTS 命中。



## 4. 代码质量与安全

| 验收项 | 结果 | 说明 |
|--------|------|------|
| 前端源码结构检查 | PASS | `qa/js_balance_check.py dist/js/app.js` → 括号配平、无 UTF-8 BOM |
| 函数源码结构检查 | PASS | 同上对 `functions/handler.ts` |
| 上游请求超时 | PASS | `AbortSignal.timeout(12000)`，前后端均有 |
| 保存成功判定 | PASS | 需 2xx **且**响应含 `records`/`saved`/`changed`，否则返回 502 `memory_not_confirmed` |
| 失败保留用户输入 | PASS | 保存失败路径不清空文本框，只报错 |
| 不使用 localStorage 模拟记忆 | PASS | 召回结果只来自 Function 返回的 PowerContext `preference` |
| 无匿名记忆读取端点 | PASS | `/debug/memory` 已移除；记忆路由全部要求验签 session |
| Scope 跨冷启动连续 | PASS（设计） | `scope_id` 编码在 30 天 HMAC token 内，不依赖进程内缓存 |
| 密钥不外泄 | PASS | Secret 只读于服务端环境；日志与前端响应不含 Token；sessionId 不回显给第三方 |

## 5. 待完成项

- [x] PowerContext 恢复后执行 `python qa/live_acceptance.py` → 2026-11-03 06:33:52 UTC **退出码 0，13/13 PASS**（见 §3.5，证据文件 `evidence/live.json`）
- [x] 浏览器补测：保存偏好 → 刷新 → 召回回填文本框 → 周报章节顺序随偏好翻转 → 独立访客隔离（见第 2 节第 5–8 行，06:35–06:39 UTC）
- [x] 线上产物与源码逐字节核对（`python qa/submission_gate.py --live`）
- [x] 交付包重建与哈希登记（见 `docs/SUBMISSION.md`）
- [x] 本地 Git 分支 `2026-competition-ecosystem` 与提交
- [ ] 推送到比赛仓库：本机无远端配置、无 `gh` CLI，需你提供仓库地址并授权
- [ ] `docs/SUBMISSION.md` 的 Qoder UID 仍需你本人提供，不由我代填

**仍需注意的稳定性风险（不影响当前 PASS，但影响评委复现）**：线上 `POWERCONTEXT_URL` 实际生效的是 Codespaces 隧道地址（`upstream_host_sha256 = 069e2c2c`）。该地址随实例闲置失效，且 2026-11-03 曾因端口 Visibility=Private 而对匿名客户端返回空 404。若你希望改用 Cloudflare 隧道，更新 Secret 后**必须**再走一次"新 `actionId` → `prepare_site` → `publish_site`"，Function 才会读到新值（复用旧 `actionId` 的 publish 是幂等空操作，不会刷新环境变量）。
