# 梦境失物招领局

一款会记住玩家上次选择的互动文字游戏。填写虚构昵称、失物与行动，夜班柜员生成剧情；使用同一昵称再次进入，会读取以前的登记继续回应。

本作品实际使用 Dify 1.18.0 编排5个节点：开始 → HTTP读取PowerContext → HTTP调用真实Qwen → HTTP保存PowerContext → 结束。使用 Dify 原生表单编码安全传递引号与换行，不需要额外 Sandbox 或插件。PowerContext1.2.0 负责真实持久化Memory及全文检索，本地Qwen2.5-0.5B生成回复。

## 运行

Linux x86_64 安装 Docker，在本目录执行：

```bash
bash run.sh
```

首次构建联网下载固定版本依赖与模型。看到 `DIFY_POWERCONTEXT_REAL_MODEL_GAME_READY port=8080` 后，打开 http://127.0.0.1:8080 。运行不需要外网、外部账号或模型密钥。

```bash
docker build -t dream-dify-complete:local .
docker volume create dream-dify-data
docker run --name dream-dify-game --cpus=2 --memory=3g --pids-limit=256 -p 127.0.0.1:8080:8080 -v dream-dify-data:/data dream-dify-complete:local
```

默认容器前台监督真实 Dify API及worker、PostgreSQL15、Redis7、PowerContext与Qwen；不需要宿主机再启动其它服务或在容器内调用Docker。网页 /api/play 会调用实际发布的Dify Workflow API。/health 初始化中为503，所有服务和DSL发布完成为200。Dify管理接口只在容器内127.0.0.1监听，不对外开放。

所有私有令牌和密码随机生成，写在/data/private，权限0600/0700。数据卷还保存/data/postgres、/data/memory和/data/logs；保留卷可跨重启延续记忆。不要公开数据卷或私有文件。

## 验证样例

用新虚构昵称，第一轮失物“会说话的蓝雨伞”，行动“给雨伞写一封道歉信”，预期读取历史=否、记忆保存=是。第二轮保留昵称，行动“询问柜员上次登记了什么”，预期读取历史=是、记忆保存=是，并提及上次失物和行动。每轮返回真实workflow_run_id。新昵称不应读取旧昵称的记忆；容器重启后同昵称仍能延续。

## 材料

app.yml 是唯一完整Dify DSL。backend/app.py 提供玩家入口与真实SDK适配，backend/supervise.py 负责前台监督和私有配置，backend/bootstrap_dify.py 通过官方Dify服务导入并发布DSL。scripts/fetch_dependencies.py 与 backend/fetch_runtime.py 固定资源下载并校验SHA256；backend/requirements.txt 锁定依赖，独立虚拟环境不污染Dify。Dockerfile固定官方镜像摘要及PostgreSQL/Redis版本。evidence/ 提供实际默认容器验收与两轮工作流记录。

模型规模较小，剧情语言质量有限。昵称是虚构记忆分区，不是身份认证，只输入虚构信息。验收证据不等同赛事正式分数，正式结果以对应提交任务为准。
