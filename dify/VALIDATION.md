# 真实运行验收

本作品实际使用 Dify 1.18.0、未修改的官方 PowerContext 1.2.0 和本地 Qwen2.5-0.5B-Instruct。源码与默认 Docker 入口均已验证。

- `evidence/standalone_backend.log`：默认容器入口，2 CPU / 2 GiB、network=none，不提供外部令牌或模型地址；真实模型生成及 Memory 写入、读取通过。
- `evidence/standalone_fullstack.log`：默认容器启动后连接实际 Dify，将交付 DSL 导入并发布，完成两轮真实 Workflow API 调用。
- `evidence/standalone_report.json`：第一轮无历史，第二轮加载历史，两轮均保存成功；PowerContext 读回两条记录，Memory revision=2。
- `evidence/standalone_turn1.json`、`standalone_turn2.json`：上述真实工作流原始响应，含工作流运行标识。
- `evidence/public_demo_acceptance.json`：游戏网页 API 也执行两轮真实已发布 Dify 工作流，无固定模型响应。

复现完整 Dify 流程：Linux x86_64 安装 Python 3.12、Docker Engine 与 Compose v2，在本目录执行 `bash run.sh`。初次安装需下载模型及 Dify 镜像。成功标志为 `DIFY_FULL_STACK_ACCEPTANCE_PASS`。

这些记录是实际运行证据；正式成绩以赛事平台结果为准。


Source-only delivery: official PowerContext wheel is fetched by scripts/fetch_dependencies.py into private runtime and SHA256-verified. Dify upstream Docker configuration is included as text and verified against deployment/upstream_manifest.json. No wheel/model binary is committed. Full game source, DSL, deployment scripts, dependency locks and real workflow evidence are included.
