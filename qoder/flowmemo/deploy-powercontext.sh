#!/bin/bash
# PowerContext 1.4.1 - Codespaces 部署脚本
# 独立安装，不修改 seekdb 内核

set -e

PORT="${PORT:-18080}"
BASE="http://localhost:${PORT}"

echo "=== PowerContext 部署开始（端口 ${PORT}）==="

# 1. 创建独立数据目录
POWERCONTEXT_HOME="/workspaces/powercontext"
DATA_DIR="${POWERCONTEXT_HOME}/data"
mkdir -p "${DATA_DIR}"

# 2. 克隆官方仓库（如果尚未存在）
if [ ! -d "${POWERCONTEXT_HOME}/powercontext" ]; then
  cd "${POWERCONTEXT_HOME}"
  git clone https://github.com/oceanbase/powercontext.git
  cd powercontext
else
  cd "${POWERCONTEXT_HOME}/powercontext"
  git pull
fi

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
# PORT 必须与 Qoder Sites Secret POWERCONTEXT_URL 里的转发端口一致。
# 当前线上 Secret 指向 ...-18080.app.github.dev，所以这里必须是 18080；
# 若服务在 8000 上正常启动而 Secret 仍指向 18080，转发层会对所有路径返回 404，
# 线上表现为健康检查 unavailable + 记忆操作 502 powercontext_failed。
cat > .env << EOF
# PowerContext 配置
POWERCONTEXT_VERSION=1.4.1
DATA_DIR=${DATA_DIR}

# 认证配置
ENABLE_AUTH=true
AUTH_TOKEN=$(openssl rand -hex 32)

# 服务配置
HOST=0.0.0.0
PORT=${PORT:-18080}

# SQLite 持久化
DATABASE_URL=sqlite:///${DATA_DIR}/powercontext.db
EOF

# 5. 初始化数据库
python -m powercontext.cli init --data-dir "${DATA_DIR}"

# 6. 启动服务（后台运行）
nohup python -m powercontext.server \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --data-dir "${DATA_DIR}" \
  --auth-enabled \
  > ${DATA_DIR}/powercontext.log 2>&1 &

echo $! > ${DATA_DIR}/powercontext.pid

# 7. 等待服务启动
sleep 3

# 8. 健康检查
echo "=== 健康检查 ==="
curl -s http://localhost:${PORT}/health/ready | jq .

# 9. 输出配置信息
echo ""
echo "=== 部署完成 ==="
echo "服务地址：http://localhost:${PORT}"
echo "认证 Token: $(grep AUTH_TOKEN .env | cut -d= -f2)"
echo "数据目录：${DATA_DIR}"
echo "日志文件：${DATA_DIR}/powercontext.log"
echo ""
echo "=== 测试命令（与 handler.ts 实际使用的契约一致，已用线上日志验证）==="
echo "# 1. 健康检查"
echo "curl -s http://localhost:${PORT}/health/ready"
echo ""
echo "# 2. 创建 Scope —— 字段必须是 title/summary/idempotency_key；"
echo "#    发送 {\"name\": ...} 会被拒绝为 422 invalid_access_request"
echo "curl -X POST http://localhost:${PORT}/v1/scopes \\"
echo "  -H 'Authorization: Bearer <token>' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"title\":\"flowmemo-test\",\"summary\":\"FlowMemo acceptance scope\",\"idempotency_key\":\"flowmemo-test-1\"}'"
echo ""
echo "# 3. 保存记忆 —— 返回 {\"changed\": bool, \"records\": [...]}，records 非空才算写入成功"
echo "curl -X POST http://localhost:${PORT}/v1/memory/remember \\"
echo "  -H 'Authorization: Bearer <token>' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"scope_id\":\"<scp_...>\",\"kind\":\"preference\",\"text\":\"周报先写风险，再写成果\"}'"
echo ""
echo "# 4. 召回 —— 响应数组字段是 hits，不是 results"
echo "curl -X POST http://localhost:${PORT}/v1/memory/search \\"
echo "  -H 'Authorization: Bearer <token>' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"scope_id\":\"<scp_...>\",\"mode\":\"fts\",\"query\":\"weekly report preference\",\"limit\":50}'"
echo ""
echo "# 5. Scope 全量清点（FTS 未命中时的兜底路径）"
echo "curl -X POST http://localhost:${PORT}/v1/memory/entries/list \\"
echo "  -H 'Authorization: Bearer <token>' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"scope_id\":\"<scp_...>\",\"limit\":100}'"
echo ""
echo "=== 注意 ==="
# The Codespaces forwarded URL disappears on idle timeout; the Site Secret
# then points at a dead host and every memory call 404s. Re-Point and re-publish.
echo "Codespaces 转发地址（...-<PORT>.app.github.dev）会随容器闲置而失效。"
echo "服务恢复后若端口/主机名变化，必须更新 Qoder Sites Secret POWERCONTEXT_URL，"
echo "并用新的 actionId 重新 prepare_site + publish_site，否则线上仍指向旧地址。"
echo ""
# A Private forwarded port answers HTTP 404 with an empty body to every client
# that has no GitHub session cookie. The Qoder Sites Server Function never has
# one, so the port must be explicitly set to Public in the Codespaces Ports tab.
echo "【关键】转发端口的 Visibility 必须设为 Public（VS Code 底部 PORTS 面板 →"
echo "该端口 → Visibility → Public）。Private 端口只认浏览器的 GitHub 登录 Cookie："
echo "自己打开是 200，Qoder Sites Server Function 与 curl 会收到 GitHub 隧道层返回的"
echo "空 body 404（响应头 x-served-by: tunnels-prod-rel-*，无 content-type）。"
echo "核验命令（不带任何 Cookie，必须返回 JSON 才算可用）："
echo "  curl -i https://<codespace>-${PORT}.app.github.dev/health/ready"
