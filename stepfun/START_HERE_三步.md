# StepFun - 快速启动指南

本项目使用 Docker seekdb Server 模式。

在比赛仓库根目录执行以下命令：

```bash
cd stepfun
npm ci --legacy-peer-deps
bash scripts/01_seekdb_docker.sh
bash scripts/02_download_models.sh
bash scripts/03_start_site.sh
```

在 VS Code PORTS 中打开 5173 端口。
详细使用说明与实测结果见 README.md。
