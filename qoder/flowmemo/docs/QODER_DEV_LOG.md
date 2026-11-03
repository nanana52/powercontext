# QODER_DEV_LOG — Qoder 开发日志

## 开发时间线

### 2026-11-02 — 项目初始化与核心开发

#### 阶段 1：需求分析
- 阅读 `AGENT_TASK.md`、`PROJECT_SPEC.md`、`qa/acceptance.md`
- 分析 `fixtures/demo_notes.json` 数据结构
- 确认 PowerContext API 端点和认证方式

#### 阶段 2：架构设计
- 选择 Python FastAPI + SQLite + 原生 HTML/CSS/JS 技术栈
- 原因：本地环境无 Node.js，Python 3.8 可用，FastAPI 轻量高效
- 前端零构建步骤，直接由 FastAPI 托管静态文件

#### 阶段 3：后端开发
- `server/database.py`：SQLite 数据层，支持 visitor/project/note/task/decision/risk/memory_log
- `server/parser.py`：基于规则的笔记解析引擎，识别待办/决定/风险
- `server/powercontext.py`：PowerContext HTTP 客户端，真实调用 API
- `server/report.py`：周报生成器，支持记忆偏好影响章节顺序
- `server/app.py`：FastAPI 主应用，整合所有模块

#### 阶段 4：前端开发
- `static/css/style.css`：暖白纸感主题，响应式三栏布局
- `static/js/app.js`：完整应用逻辑，API 交互，状态管理
- `static/index.html`：工作台主页面

#### 阶段 5：测试验证
- 解析器测试：2 notes → 4 tasks, 2 decisions, 2 risks ✓
- API 测试：session, import, task toggle, report generation ✓
- 浏览器测试：页面加载、演示导入、任务完成、周报生成 ✓
- 重复导入防护：第二次导入不产生重复数据 ✓

#### 阶段 6：文档编写
- README.md：项目说明和快速开始
- docs/RUNBOOK.md：运行与部署手册
- docs/DEMO_STEPS.md：演示步骤
- docs/EVIDENCE.md：验证证据
- docs/SUBMISSION.md：提交材料
- docs/QODER_DEV_LOG.md：本文件

### 2026-11-03 线上发布与调试（Qoder Sites）

**问题定位 1 — 发布产物长期停留在旧版本（决定性发现）**

多轮"重新发布"后线上 `/js/app.js` 仍是旧内容。用 `curl` 带 `?v=` 破缓存参数直接抓取，返回的仍是旧的 19786 字节文件，证明**不是浏览器缓存**，而是发布链路本身。

根因：站点描述符 `.FlowMemo 周报工作台.qoder.site` 内冻结了 `prepare_site` 当时的 `indexHtml` 快照与 `artifactSha256`。复用同一个 `actionId` 调 `publish_site`，重复部署的是这份**不可变草稿快照**，磁盘上的新文件从未被打包。

修复：每次内容变更必须使用**新的 `actionId` 重新执行 `prepare_site`**，再发布新草稿。验证：新快照发布后线上 `index.html` 含 `diagnosticLog`、脚本路径为带版本号的 `js/app.js?v=`、`/js/app.js` 为 25270 字节且包含 `addDiagnostic`，与本地源码一致。全程沿用同一 `projectId`/`siteId`，未创建第二个站点。

**问题定位 2 — 健康状态永久停在"检测中…"**

旧 `checkPowerContextHealth()` 只弹一个瞬时 toast，从不回写 `#memoryStatusText` 与 `#memoryBadge`；`api()` 也没有超时。修复后：所有分支都写状态，12 秒超时，成功显示"已连接 PowerContext"，失败显示真实错误类别（未配置 / 不可达 / 上游 HTTP 状态码），并在页面底部渲染脱敏诊断日志。

**问题定位 3 — Scope 连续性**

旧 `idempotency_key` 拼了 `Date.now()`，Function 冷启动会新建 Scope 并孤立已写入的记忆。现方案改为把 `scopeId` 写进 HMAC 签名 session token，前端持久化 token 并在刷新时回传，服务端验签后复用同一 Scope；`idempotency_key` 只在真正新建访客会话时随机。

**安全收紧**

- 移除匿名 `/debug/memory` 端点（原先可泄露记忆内容与 Scope）。
- Scope 只从验签 token 读取，拒绝调用方自带 `scope_id`，`visitorId` 由服务端生成。
- 保存成功必须满足"2xx + 响应含 `records`/`saved`/`changed`"，否则保留用户输入并报错。

**新增可复现验收脚本**：`qa/live_acceptance.py`（纯标准库，打线上 Function）。PowerContext 未就绪时输出 `BLOCKED` 并以退出码 2 结束，不把未执行的用例谎报为通过。

**问题定位 4 — 线上页面写了做不到的操作**

`待办事项` 标签写着"（双击编辑）"，但部署版 `app.js` 从未绑定 dblclick；同时 `setConnectionStatus` 写入的 `success`/`error` 类名与 `style.css` 中定义的 `ok`/`err` 不一致，诊断条目取不到配色。修复：文案改为"（点击左侧圆点切换完成）"、类名对齐、并去掉 `memoryInput` 上预填的示例值（它让人误以为偏好已保存）。

**最终一轮发布与线上取证（`actionId 9c37e96b-4a51-46a7-a60e-3ab694f4c62f`）**

- 线上 `index.html` 脚本路径 `js/app.js?v=20261103-5`，源码 26 个元素 id 全部出现；`/js/app.js` 返回 25270 字节，SHA-256 与 `dist/js/app.js` 相同。
- 浏览器实测：状态栏渲染为真实错误 `PowerContext /health/ready 返回 HTTP 404`，不再停在"检测中…"；载入演示 KPI 2/4/2/2；勾选待办 → `task-item done` → reload 后仍保留；关电状态下点"保存偏好"提示"请先连接 PowerContext"且**输入框内容保留**。
- Function 路由面实测：`/debug/memory` → 404，`/session/ensure` → 502 且带 `upstream_status: 404`，证明请求真的打到 PowerContext。
- 新增可在离线执行的签名防伪用例（伪造/篡改 token 三处均 401），把第 8 项拆成"可测的一半"与"需服务的一半"。

**部署描述符不会自动更新**：`prepare_site` 返回 `descriptorStatus: "pending"` 时磁盘上的 `.qoder.site` 仍是旧快照，而线上其实已经发布了新草稿。结论：判断线上状态只能靠直接抓取产物，不能读本地描述符。

**问题定位 5 — 核验证据抽屉永远打不开**

`style.css` 用 `display:none` 定义 `.evidence-drawer`，显示靠 `.open` 类；而 `app.js` 的开关只翻转 `content.hidden` 属性。两者互不相干，所以点击「▸ 核验证据」在 DOM 上改了 `hidden`，画面上却始终空白。第一轮浏览器测试读 `drawer.hidden` 得到 `true/false` 变化，误判为可用；改读 `getComputedStyle(...).display` 才暴露问题。修复为同时切换 `.open` 类与 `hidden`，并让箭头在 `▸/▾` 间翻转。线上复测：`before: none → opened: block → closedAgain: none`。

**问题定位 6 — 召回链路缺 `/v1/context/prepare`**

`PROJECT_SPEC.md` 与 `AGENT_TASK.md` 把「服务端调用 `/v1/memory/remember` 写入、`/v1/context/prepare` 读回」列为强制要求，而线上 Function 只用了 `search` + `entries/list`。现已在 `recallPreference()` 开头真实调用 `prepare`（`{scope_id, query, max_bytes: 4000}`）。由于 `prepare` 返回的是拼装后的 `content` 文本而非条目，它的结果只在结构化路径无法定论时按前缀提取使用；`prepare` 失败仅记日志，不会让召回整体不可用。

**问题定位 7 — 外部依赖故障无法定位**

Codespaces 转发地址与应用端口不一致时，站点只会看到 `upstream_status: 404`，无法区分"实例停机"与"端口不对"。`/health` 现在额外返回 `upstream_port`（只取转发 URL 里的端口号，不含主机名），实测返回 `18080`。`deploy-powercontext.sh` 旧版硬编码 `--port 8000`，因此若评审者或我方按旧脚本重启实例，进程会监听 8000 而 Secret 仍指向 18080，线上将继续 404。脚本已改为 `PORT="${PORT:-18080}"`。

诊断输出只给端口号，不含主机名，也不含任何凭据。

**问题定位 8 — 404 的真实原因是端口可见性，不是端口号也不是实例停机**

后续取证确认：Codespaces 转发端口若设为 Private，匿名客户端（Server Function、curl）会对**所有路径**返回 `content-length: 0` 的空 404，且响应头来自 `x-served-by: tunnels-prod-rel-*` 隧道层；用一个不存在的主机名做对照探针可得到逐字节相同的答案，因此"私有端口"与"实例不存在"在响应上不可区分，而登录态浏览器仍能拿到 200 `status=ready`。把 Ports → Visibility 改为 Public 后，Function 侧 `/health/ready` 立刻返回 HTTP 200 + `application/json`。`deploy-powercontext.sh` 与 `docs/RUNBOOK.md` 已写入该自查步骤。

**问题定位 9 — 上游返回 HTML 却被记成"成功"**

`pcCall()` 旧版对无法 JSON 解析的响应体返回空对象，非 2xx 也不抛错，导致代理页/登录页的 2xx HTML 可能被算作一次成功的记忆写入。现改为返回 `parsedJson`/`contentType`/`servedBy`/`bodyPrefix`，并新增 `requirePcOk()`：非 2xx **或** 2xx 非 JSON 一律抛出 `UpstreamError`，错误载荷带上 `upstream_content_type`。`/health` 用 `upstream_json` 而不是状态码来判定就绪，前端据此显示"返回非 JSON 响应（HTTP …，Content-Type=…）"。

**问题定位 10 — 改了 Secret 但线上仍在用旧地址**

`POWERCONTEXT_URL` 更新后 `/health` 仍回显旧主机。原因是 Function 的环境变量在**部署时快照**，而用同一个 `actionId` 再调 `publish_site` 是幂等 no-op（返回同一个 `publishOperationId`）。结论：内容变更与 Secret 变更都必须换**新的 `actionId`** 走 `prepare_site` → `publish_site`。为在不暴露主机名的前提下证明这一点，`/health` 增加 `upstream_host_kind` 与 `upstream_host_sha256`（主机名 SHA-256 前 8 位）。

**发布轮次**：`3f7c1a92-8d45-4c6b-9f0e-2b5ad7e64108` → `6b2e9c44-1f77-4d3a-b0c5-8e94fa27c3d1`（含 `.open` 抽屉修复、`/v1/context/prepare` 召回链路、`upstream_port` 诊断）→ `d7423740-f00e-4539-8d26-04d0afb4fb13`（当前线上版本，含非 JSON 硬失败、`upstream_host_kind`/`upstream_host_sha256` 诊断与 `?v=20261103-6` 前端）。每轮都使用新的 `actionId` 重新 `prepare_site`，`siteId` 始终未变。

**最后一轮全绿（2026-11-03 06:33–06:45 UTC）**

- Function → PowerContext：`GET /functions/v1/app/health` 返回 `upstream_status:200`、`upstream_json:true`、`upstream_content_type:application/json`、`health.status:"ready"`、`request_id:c3bbc658c1bce747`。`upstream_host_sha256=069e2c2c` 对应恢复后的 Codespaces 公网隧道主机，证明线上实际打到的就是这个地址。
- `python qa/live_acceptance.py --output evidence/live.json` → **退出码 0，13/13 PASS**（Scope 创建、真实保存、刷新召回、`latest_preference_wins`、访客隔离、伪造/篡改 token 401、`/debug/memory` 404、外部 token 拒绝、任意 `scope_id` 忽略）。
- 浏览器 8 项功能全部 PASS，含偏好真实翻转周报章节顺序（`已完成→风险→…` ↔ `风险→已完成→…`）与"保存回执到达后才清空文本框"。完整取证见 `docs/EVIDENCE.md` §2、§3.0、§3.5。

**问题定位 8 — 404 的真实原因是端口可见性，不是端口号也不是实例停机**

**问题定位 11 — 交付包里装着上一版包的校验和**

`qa/build_package.py` 只排除了 `.zip` 本体，没排除包外的 `flowmemo-submission.zip.sha256`，于是**上一轮**产物的摘要被当成材料打进**新一轮**交付包（条目数 43）。评审据此核对会拿到一个描述不存在文件的哈希。现同时排除 `ARCHIVE` 与 `SIDECAR`，条目数回到 42；`docs/SUBMISSION.md` 也改为只指向包外校验和，不再内嵌会被自身编辑作废的摘要。

### 技术决策记录

1. **发布形态**：Qoder Sites 静态前端 + Server Function（Deno）
   - 原因：Token 不能进浏览器；站点无自建服务器
   - 约束：`prepare_site` 生成不可变草稿，改内容必须换新 `actionId`

2. **项目数据持久化**：浏览器 `localStorage`
   - 原因：无共享后端需求，演示数据为虚构
   - 代价：清浏览器数据或换设备会丢失记录（已在 README 明示）

3. **记忆持久化**：PowerContext 真实 Scope
   - 原因：竞赛核心是"跨会话真实记忆"，不允许 localStorage 模拟
   - 实现：签名 session 绑定 `scope_id`，`search(hits)` + `entries/list` 双路径召回

4. **周报生成**：模板 + 规则引擎
   - 原因：不依赖外部 AI 模型，100% 可预测
   - 特性：记忆偏好实际决定章节顺序

### 待完成项

- [x] Qoder Sites 公开发布
- [x] 无痕窗口验证（线上产物与源码一致性已由 curl 直接证明）
- [x] 前端初始化与健康状态真实显示
- [x] PowerContext 服务恢复后的记忆保存/召回/偏好生效/访客隔离线上验证（2026-11-03，13/13 + 8/8 PASS）
- [ ] Git 提交并推送到比赛仓库（提交已在本地分支完成；推送需比赛仓库地址与授权）

