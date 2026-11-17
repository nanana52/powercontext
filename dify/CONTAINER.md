# 默认容器与完整 Dify 部署

在本目录构建：

```bash
docker build -t dream-lostfound:local .
docker volume create dream-memory
docker run --name dream-backend --cpus 2 --memory 2g --pids-limit 128 -p 127.0.0.1:18090:18090 -v dream-memory:/data dream-lostfound:local
```

默认入口会启动真实本地 Qwen 模型和 PowerContext 后端，并在数据卷生成私有的 `/data/access.token`。无须外部模型密钥；容器启动后的模型推理不需要网络。构建阶段需下载依赖，模型和运行时均校验 SHA256。容器以前台进程运行，使用 UID 10001，记忆写入 `/data/memory.db`。

此容器是 Dify 的配套服务。完整 Dify 安装、DSL 导入发布和两轮验收由 `bash run.sh` 完成，详见 README.md。已有 Dify 时，可导入 app.yml，将 POWERCONTEXT_BASE_URL 配置为实际可达的容器地址，并把数据卷内的令牌填入 Dify 秘密环境变量 POWERCONTEXT_TOKEN。令牌不要放入源码或公开资料。

容器发布端口示例绑定 localhost；Dify 在另一容器内时，应通过 Docker 网络或宿主机网关连接，按部署实际地址配置。不要把 `127.0.0.1` 当作另一容器的地址。

## 可选游戏网页

`demo/app.py` 仅提供游戏表单与 `/api/play`，调用真实已发布 Dify Workflow。将私有配置写在仓库外的 JSON 文件中（字段 `api_url` 与 `app_key`），设置 DREAM_DEMO_CONFIG 指向该文件，然后用已安装后端依赖的 Python 启动：

```bash
DREAM_DEMO_CONFIG=/private/demo.json python -m uvicorn demo.app:app --host 127.0.0.1 --port 18110
```

昵称、失物和行动是玩家输入；Dify 应用密钥保留在服务端。使用同一昵称连续两轮即可检查记忆延续。临时 HTTPS 预览如在 PREVIEW.md 列出，只在相关进程运行时有效；代码及本地部署不依赖它。
