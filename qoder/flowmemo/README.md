# FlowMemo — 会记忆的周报工作台

面向学生实验室、小团队与个人的「零碎工作记录 → 可追溯待办 → 周报」工具。核心差异点是接入 **PowerContext** 真实记忆服务：用户主动保存的周报写作偏好会写入服务端 Scope，刷新或重开网站后从 PowerContext 召回，并真实影响生成周报时的章节顺序。

- 线上地址：<https://flowmemo-workspace-7u2qbfllad4.qoder.zone/>
- 部署形态：Qoder Sites 静态前端 + Qoder Sites Server Function（Deno）+ 外部 PowerContext 1.4.1 HTTP 服务
- 无记忆 mock：浏览器不直连 PowerContext，也不使用 localStorage 伪装记忆召回

## 1. 运行与演示

线上站点直接打开即可，无需本地环境。演示步骤见 [docs/DEMO_STEPS.md](docs/DEMO_STEPS.md)。

本地预览静态前端：

```bash
cd qoder/flowmemo/dist
python -m http.server 8901     # http://127.0.0.1:8901
```

本地预览下记忆相关请求会失败（Server Function 只存在于已部署站点），前端会明确显示"未连接 + 真实错误"，不会假装成功。基础记录、待办、周报功能仍可用。

## 2. 实际部署架构

```
┌──────────────────────────────────────────────────────────┐
│  浏览器：qoder/flowmemo/dist/                             │
│  index.html + js/app.js + css/style.css                  │
│  · 项目数据（记录/待办/决策/风险）→ localStorage            │
│  · 记忆操作 → 同源 fetch /functions/v1/app/*              │
│  · 页面内诊断日志（脱敏：状态码、命中数、request id）        │
└───────────────────────┬──────────────────────────────────┘
                        │ 同源 HTTP
┌───────────────────────▼──────────────────────────────────┐
│  Qoder Sites Server Function：functions/handler.ts        │
│  · HMAC-SHA256 签名 session（visitorId/projectId/scopeId/exp）│
│  · /health  /session/ensure  /memory/preference/save      │
│    /memory/preference/recall                              │
│  · 12s 超时 + 上游状态码校验；密钥只留在服务端              │
└───────────────────────┬──────────────────────────────────┘
                        │ Bearer Token（服务端 Secret）
┌───────────────────────▼──────────────────────────────────┐
│  PowerContext 1.4.1                                        │
│  GET /health/ready · POST /v1/scopes                       │
│  POST /v1/memory/remember → {changed, records}             │
│  POST /v1/memory/search   → {mode, hits}                   │
│  POST /v1/memory/entries/list → {entries}                  │
└──────────────────────────────────────────────────────────┘
```

服务端 Secret（只存在于 Qoder Sites 私密配置，源码、日志与本文档均不含值）：`POWERCONTEXT_URL`、`POWERCONTEXT_TOKEN`。
Session 签名密钥优先使用独立 Secret；当前部署回落到服务端已有的 PowerContext Token 签名，不使用任何公开常量密钥。

## 3. 目录说明

| 路径 | 作用 |
|------|------|
| `dist/index.html`、`dist/js/app.js`、`dist/css/style.css` | **线上实际发布的前端产物**（版本化脚本路径 `app.js?v=`） |
| `functions/index.ts`、`functions/handler.ts` | **线上实际发布的 Server Function** |
| `.FlowMemo 周报工作台.qoder.site` | Qoder Sites 生成的站点描述符（不要手写修改） |
| `qa/live_acceptance.py` | 打线上 Function 的可复现验收脚本（stdlib，无 mock） |
| `qa/powercontext_smoke.py` | 直连 PowerContext 的真实写入+召回冒烟测试 |
| `qa/js_balance_check.py` | 前端/函数源码结构与编码静态检查 |
| `fixtures/` | 虚构演示数据 |
| `docs/` | 部署、运行手册、开发记录与证据 |
| `server/`、`static/`、`run.py`、`requirements.txt` | 早期本地 Python 原型，**未部署**，仅作演进留档 |

> 仓库根目录的 `dist/`、`functions/` 与 `qoder/flowmemo/` 下的同名文件内容完全一致（SHA-256 校验通过）。发布使用 `qoder/flowmemo/dist` 与 `qoder/flowmemo/functions`。

## 4. 记忆契约（真实行为）

1. **建立会话**：`POST /session/ensure`。首次调用由服务端生成 `visitorId` 并向 PowerContext 真实创建 Scope（返回 `scp_…`）；签发 30 天有效的 HMAC 签名 token，前端存入 `localStorage` 并在刷新时回传校验。
2. **保存偏好**：`POST /memory/preference/save`。写入文本带固定前缀 `FlowMemo weekly report preference: `；必须等到 PowerContext 返回 2xx **且**响应含 `records`/`saved`/`changed` 才判定成功，成功后才清空输入框，并在 token 中绑定该偏好的 SHA-256。失败时保留用户输入并显示真实错误。
3. **召回偏好**：`POST /memory/preference/recall`。先真实调用赛题要求的 `POST /v1/context/prepare`（`{scope_id, query, max_bytes}` → `{status, content}`）；随后用 `search`（`mode: fts`，读取 `hits`）做结构化定位，`hits` 为空或 token 带 `prefHash` 约束时再用 `entries/list` 全量清点并按时间取最新。只有当结构化路径无法定论时才从 `prepare` 的 `content` 文本中按前缀提取；若带 `prefHash` 却检索不到完全匹配项，**不会**退化返回更旧的偏好。
4. **影响周报**：`生成周报` 先召回偏好，再按偏好文本中各章节关键词出现位置排序章节（未提及的章节保留在末尾，不丢信息）。报告头部标注"PowerContext 记忆偏好已应用"或"使用默认章节顺序"。
5. **访客隔离**：Scope 只从已验签 token 中取得；接口不接受调用方自带的 `scope_id`，也没有匿名读取记忆的端点。

## 5. 验证方式

```bash
cd qoder/flowmemo
python qa/live_acceptance.py                       # 线上 Function 契约验收
python qa/live_acceptance.py --output evidence/live.json
python qa/powercontext_smoke.py --url "$POWERCONTEXT_URL" --output evidence/pc.json
python qa/js_balance_check.py dist/js/app.js
python qa/submission_gate.py --live          # 线上产物与源码逐字节核对
python qa/build_package.py                   # 重建交付包 + 包外校验和
```

`live_acceptance.py` 在 PowerContext 未就绪时输出 `BLOCKED` 并以退出码 2 结束，不会把未执行的用例谎报为通过。

## 6. 已知限制

- 项目数据保存在浏览器 `localStorage`：清浏览器数据或换设备会丢失记录。
- PowerContext 当前托管在 GitHub Codespaces 转发的临时地址，实例停止后站点记忆功能进入"未连接 + 真实错误"状态，基础功能仍可用。生产化方案见 [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)。
- 匿名访客身份来自服务端签发的 token，清除 `localStorage` 等于换一个新的 PowerContext Scope。

## 7. 安全说明

- Token、Secret 值与完整 session id 不出现在源码、前端、日志或本文档中。
- 已移除早期可匿名读取记忆内容与 Scope 的 `/debug/memory` 端点。
- 所有上游请求带 12 秒超时，健康检查不会长期停留在"检测中…"。

## 许可证

OceanBase × Qoder 2026 竞赛参赛作品。
