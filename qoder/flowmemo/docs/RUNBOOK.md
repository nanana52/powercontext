# RUNBOOK — FlowMemo 运行与部署手册

## 0. 线上部署运行（参赛版本，Qoder Sites）

- 站点：<https://flowmemo-workspace-7u2qbfllad4.qoder.zone/>
- 发布产物：`qoder/flowmemo/dist`（静态前端）+ `qoder/flowmemo/functions`（Server Function，入口 `index.ts` → `Deno.serve(handler)`）
- 服务端 Secret（Qoder Sites 私密配置，只有名称进入草稿声明，值不落盘）：`POWERCONTEXT_URL`、`POWERCONTEXT_TOKEN`

### 重新发布（关键约束）

```text
1. 修改 dist/ 或 functions/ 源码
2. 生成新的 actionId（复用旧 actionId 会重复部署 prepare_site 当时的冻结快照，
   磁盘新文件永不生效 —— 这是本项目此前"改了却没上线"的根因）
3. prepare_site(projectRoot, webDirectory=qoder/flowmemo/dist,
   functionDirectory=qoder/flowmemo/functions, projectId=01a19d11-54b8-…,
   secretNames=[POWERCONTEXT_URL, POWERCONTEXT_TOKEN], databaseAccess=none)
4. get_publish_status 直到 canPublish=true
5. publish_site(新 actionId)
6. 用 curl 直取线上 /index.html 与 /js/app.js?v=… 比对字节数与关键标识
```

前端脚本路径带版本参数（当前 `js/app.js?v=20261103-5`），每次改动同时递增，避免评审者被缓存挡住。

### 线上验收

```bash
cd qoder/flowmemo
python qa/live_acceptance.py            # 0=通过 1=有 FAIL 2=PowerContext 未就绪
python qa/submission_gate.py
```

### 记忆功能故障排查

| 现象 | 判读 | 处置 |
|------|------|------|
| 顶部"未连接"+ 诊断显示 `non_json_response (HTTP 404)` | 响应来自 GitHub 转发层而非 PowerContext（`upstream_served_by: tunnels-prod-rel-*`、`upstream_content_type` 为空） | 见下方"Codespaces 端口必须 Public" |
| 诊断显示 `PowerContext 返回非 JSON 响应（HTTP …，Content-Type=text/html）` | 端口为 Private，GitHub 用登录确认页代答 | 把该端口 Visibility 改为 Public |
| 顶部"未连接"+ 诊断显示 `unavailable (HTTP 404)` | PowerContext 服务停机（Codespaces 转发层 404） | 重启该 Codespace 并拉起服务；URL/Token 不变则无需改 Secret |
| `PowerContext 不可达：PowerContext network error or timeout` | Function 侧连接失败或超 12 秒 | 检查服务是否存活、端口是否转发 |
| 保存失败 `memory_not_confirmed` | 上游 2xx 但响应无 `records`/`saved`/`changed` | 查 Function 日志的 `request_id` 与上游状态码 |
| 召回为空但确实保存过 | Scope 不一致或 FTS 未命中 | 核对 token 内 `scope_id`；服务端已用 `entries/list` 兜底，仍空则查偏好文本前缀 |
| 需要临时改地址 | 换 Codespace/隧道后 URL 变化 | 更新 `POWERCONTEXT_URL` Secret 后**必须用新的 `actionId` 重新 `prepare_site` + `publish_site`**；Function 的环境变量在部署时快照，复用旧 `actionId` 的 publish 是幂等空操作，线上会继续用旧地址（`/health` 的 `upstream_host_sha256` 可用来确认实际生效的主机） |

**Codespaces 端口必须 Public（关键）**：Qoder Sites Server Function 是**不带 GitHub 会话 Cookie** 的匿名客户端。端口 Visibility 为 Private 时，你自己用登录浏览器打开 `/health/ready` 是 200，但 Function 只会拿到 GitHub 隧道层返回的**空 body 404**（响应头 `x-served-by: tunnels-prod-rel-*`、无 `content-type`）——这与 Codespace 是否正在运行无关，也和伪造一个不存在的主机名所得响应逐字节相同，因此匿名侧无法区分"端口未公开"与"主机名失效"。

处置：VS Code 底部 **PORTS** 面板 → 选中 PowerContext 监听端口 → **Visibility → Public**；若端口未列出，先 `Forward an advanced port` 按 `POWERCONTEXT_URL` 里的端口号补上。

自检（必须返回 JSON，且带 `x-powercontext-request-id`）：

```bash
curl -i https://<codespace>-<port>.app.github.dev/health/ready
```

## 1. 本地原型运行（早期 Python 版本，未部署）

> 本节描述仓库里的 `server/` + `static/` + `run.py` 原型，仅用于本地演示与历史留档，**不是**参赛线上版本。

### 前置条件
- Python 3.8+
- pip

### 步骤

```bash
# 进入项目目录
cd qoder/flowmemo

# 安装依赖
pip install -r requirements.txt

# 启动应用（默认端口 8900）
python run.py

# 浏览器自动打开 http://127.0.0.1:8900
```

### 环境变量（可选）

| 变量 | 说明 | 示例 |
|------|------|------|
| `FLOWMEMO_PORT` | 服务端口 | `8900` |
| `FLOWMEMO_HOST` | 绑定地址 | `0.0.0.0` |
| `FLOWMEMO_DB` | 数据库路径 | `./data/flowmemo.db` |
| `POWERCONTEXT_URL` | PowerContext 服务地址 | `https://api.powercontext.example.com` |
| `POWERCONTEXT_TOKEN` | PowerContext 认证令牌 | `pc_xxxx...` |

### 验证

1. 打开 http://127.0.0.1:8900
2. 点击「载入演示」→ 确认 KPI 显示 2/4/0/2
3. 勾选一个任务 → 确认「已完成」变为 1
4. 点击「生成周报」→ 确认周报包含风险、已完成、待办、决策、下周计划
5. 点击「复制」→ 确认剪贴板内容正确

## 2. PowerContext 真实接入

### 2.1 获取 PowerContext 服务

参考官方文档：https://powercontext.oceanbase.io/en/docs/develop/api-quickstart/

1. 部署或获取一个公网可达的 PowerContext 服务
2. 获取服务 URL 和认证 Token

### 2.2 配置

```bash
# Linux/macOS
export POWERCONTEXT_URL="https://your-powercontext-server.com"
export POWERCONTEXT_TOKEN="your-token-here"

# Windows PowerShell
$env:POWERCONTEXT_URL="https://your-powercontext-server.com"
$env:POWERCONTEXT_TOKEN="your-token-here"
```

### 2.3 验证连接

```bash
# 使用内置冒烟测试
python qa/powercontext_smoke.py --url "$POWERCONTEXT_URL" --output evidence/pc_result.json
```

预期输出：`POWERCONTEXT_REAL_ROUNDTRIP_PASS`

### 2.4 应用内验证

1. 启动应用后，顶栏应显示绿色「PowerContext 已连接」
2. 在记忆卡片中输入偏好并点击「保存偏好」
3. 点击「召回记忆」确认返回内容
4. 生成周报确认记忆影响章节顺序

## 3. 生产部署

### 使用 Gunicorn（推荐）

```bash
pip install gunicorn
gunicorn server.app:app -w 4 -b 0.0.0.0:8900
```

### 使用 Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8900"]
```

### Qoder Sites 部署

通过 Qoder Sites 的 Server Functions 能力部署后端，静态文件通过 Sites 托管。
详见 Qoder Sites 文档。

## 4. 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 端口被占用 | 8900 端口已被使用 | 设置 `FLOWMEMO_PORT=8901` |
| PowerContext 未连接 | 环境变量未设置 | 检查 `POWERCONTEXT_URL` |
| 数据库锁定 | 多进程写入冲突 | 使用 WAL 模式（已默认启用） |
| 前端空白 | 静态文件路径错误 | 确认 `static/` 目录存在 |
