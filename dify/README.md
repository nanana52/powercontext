# 梦境失物招领局

一个会记住玩家失物和行动的互动文字游戏。每轮输入昵称、虚构失物和行动；使用同一昵称再次进入时，柜员读取以前的登记并延续剧情。

Dify Workflow 负责输入清洗、创建玩家分区、读取历史、调用模型、写入记忆和校验输出。PowerContext 1.2.0 负责真实的持久化 Memory 与全文检索；本地 Qwen2.5-0.5B-Instruct 负责生成回复。没有用固定模型输出或模拟 Memory 代替真实运行。

## 交付入口

- app.yml：可直接导入 Dify 的应用 DSL，与 dsl/dream-lostfound.yml 完全相同。
- backend/app.py：本作品的配套服务源码。
- backend/requirements.txt：固定 Python 依赖。
- scripts/fetch_dependencies.py：未修改的官方 PowerContext 发布包，版本、来源、许可证及 SHA256 见 THIRD_PARTY.md。
- scripts/verify_full_stack.py：安装、导入发布及两轮真实工作流自动验收。
- Dockerfile: 默认 standalone local model + PowerContext backend; see CONTAINER.md.
- VALIDATION.md、evidence/compact_*.json：验证步骤和真实运行记录。

## 运行环境

Linux x86_64，Python 3.12（含 venv），Bash、curl、Docker Engine 与 Compose v2。Dify 版本为 1.18.0，DSL 版本为 0.7.0。安装时需要访问 Python 包源、ModelScope、GitHub 和 Docker 镜像源；首次冷启动需要下载约 500MB 的模型和 Dify 镜像，耗时取决于网络。

本游戏选择 Dify + PowerContext，不依赖 seekdb。PowerContext 使用 SQLite 持久化玩家记忆；这是官方 SDK 的正常后端，不是重新实现或模拟 PowerContext。

## 一条命令完整运行和验收

在 dify 目录运行：

```bash
bash run.sh
```

已有 Python 3.12 时可显式指定：

```bash
DREAM_PYTHON=/path/to/python3.12 bash run.sh
```

该命令启动真实本地模型和配套服务，创建独立 Dify 部署，初始化本地管理员，导入并发布 DSL，随后执行两轮真实 Workflow API 请求。成功标志为 DIFY_FULL_STACK_ACCEPTANCE_PASS。

所有随机密码、服务令牌和记忆数据都保存在本机 .runtime 内；不打印密钥，不随源码交付。端口默认是模型 18081、后端 18090、Dify 页面 18080。如已有服务占用，可设置 DREAM_MODEL_PORT、DREAM_BACKEND_PORT、DREAM_DIFY_PROJECT、DREAM_DIFY_API_PORT、DREAM_DIFY_WEB_PORT、DREAM_DIFY_HTTP_PORT 和 DREAM_DIFY_BACKEND_URL。

## 在已有 Dify 导入

1. 执行 bash start_backend.sh，等待 MODEL_AND_POWERCONTEXT_HEALTH_PASS。
2. 在 Dify 1.18.0 工作室导入 app.yml。
3. POWERCONTEXT_BASE_URL 设置为 Dify 容器能访问的后端地址，例如同机 Linux Docker 默认网关 http://172.17.0.1:18090。
4. 将 .runtime/access.token 填入 Dify 的秘密环境变量 POWERCONTEXT_TOKEN。不要公开或提交该文件。
5. 如私网访问被拒绝，仅放行实际后端地址，例如 SSRF_PROXY_ALLOW_PRIVATE_IPS=172.17.0.1/32，并按 Dify 部署方式重建对应服务。
6. 发布 Workflow 后可从 Dify 页面或其 Workflow API 体验。

该流程没有额外的知识库或自定义插件。真实模型通过 Workflow 的 HTTP Request 节点调用配套服务，再调用本地 Qwen；因此不能用 Dify 原生 LLM Token 统计为零来推断没有模型调用。

## 可重复验证样例

使用从未用过的昵称：

| 轮次 | 失物 | 行动 | 核验结果 |
| --- | --- | --- | --- |
| 第一轮 | 会说话的蓝雨伞 | 给雨伞写一封道歉信 | previous_memory_loaded=否，memory_saved=是 |
| 第二轮 | 会说话的蓝雨伞 | 询问柜员上次登记了什么 | previous_memory_loaded=是，memory_saved=是，并回顾上一轮内容 |

停止并重启后端，再用同一昵称访问，历史仍可读取。新的昵称应没有旧历史。Memory 的实际引用、两轮输出与运行状态见 evidence/compact_report.json、compact_turn1.json 和 compact_turn2.json。

模型规模较小，回复的语言质量和变化有限。昵称是虚构游戏记忆的分区标识，不是身份认证。只输入虚构故事，不保存现实隐私。

停止配套模型和后端可运行 bash stop_backend.sh；保留 .runtime 才能保留管理员配置和记忆。Dify 容器使用本目录运行配置管理。


Default Docker entrypoint and real Dify two-turn integration both pass; see CONTAINER.md and evidence/standalone_*. The optional demo/ UI forwards a real published Dify workflow.


Source-only delivery: official PowerContext wheel is fetched by scripts/fetch_dependencies.py into private runtime and SHA256-verified. Dify upstream Docker configuration is included as text and verified against deployment/upstream_manifest.json. No wheel/model binary is committed. Full game source, DSL, deployment scripts, dependency locks and real workflow evidence are included.
