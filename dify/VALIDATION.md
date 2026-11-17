# 可复现验证

本次实现使用官方未修改的 PowerContext 1.2.0 wheel，文件 SHA256 为 9bb55ec13bb2fc1ac84038d917042cc2890ffab4aeedacf1cd5ba5329dcb84b9。

已经完成：

1. 在独立空 Memory 数据目录启动真实配套服务；日志确认模型和 PowerContext 健康。
2. 将交付的 DSL 重新导入实际 Dify 1.18.0，创建新的已发布应用。
3. 执行两轮真实 Workflow API 请求，第一轮无历史、第二轮加载历史，两轮均保存成功。
4. 从 PowerContext Memory 读回两条记录和 revision=2 的引用。原始输出在 evidence/compact_*.json。
5. 按交付 Dockerfile 实际构建 dream-lostfound-compact:20261117。
6. 用默认容器入口、UID=10001、network=none 运行镜像，完成真实 Memory 写入和检索；记录在 evidence/compact_docker_image.log。

第6项验证的是后端容器和 Memory 的独立性；完整模型生成与 Dify 编排由第2～4项验证，不将无网络后端检查冒称为完整 Dify 无网络运行。

运行 bash run.sh 可在自己的环境进行完整验收；已有本项目 Dify 部署时，可以运行 python3 scripts/verify_full_stack.py --existing-deployment 重新导入并验证。

本地运行证据不是平台正式成绩，正式评分由赛事平台确认。
