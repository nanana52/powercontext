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
docker run --name dream-dify-game --cpus=2 --memory=2g --memory-swap=2g --pids-limit=128 -p 127.0.0.1:8080:8080 -v dream-dify-data:/data dream-dify-complete:local
```

默认容器前台监督真实 Dify API及worker、PostgreSQL15、Redis7、PowerContext与Qwen；不需要宿主机再启动其它服务或在容器内调用Docker。网页 /api/play 会调用实际发布的Dify Workflow API。/health 初始化中为503，所有服务和DSL发布完成为200。Dify管理接口只在容器内127.0.0.1监听，不对外开放。

所有私有令牌和密码随机生成，写在/data/private，权限0600/0700。数据卷还保存/data/postgres、/data/memory和/data/logs；保留卷可跨重启延续记忆。不要公开数据卷或私有文件。

## 验证样例

用新虚构昵称，第一轮失物“会说话的蓝雨伞”，行动“给雨伞写一封道歉信”，预期读取历史=否、记忆保存=是。第二轮保留昵称，行动“询问柜员上次登记了什么”，预期读取历史=是、记忆保存=是，并提及上次失物和行动。每轮返回真实workflow_run_id。新昵称不应读取旧昵称的记忆；容器重启后同昵称仍能延续。

## 材料

app.yml 是唯一完整Dify DSL。backend/app.py 提供玩家入口与真实SDK适配，backend/supervise.py 负责前台监督和私有配置，backend/bootstrap_dify.py 通过官方Dify服务导入并发布DSL。scripts/fetch_dependencies.py 与 backend/fetch_runtime.py 固定资源下载并校验SHA256；backend/requirements.txt 锁定依赖，独立虚拟环境不污染Dify。Dockerfile固定官方镜像摘要及PostgreSQL/Redis版本。evidence/ 提供实际默认容器验收与两轮工作流记录。

模型规模较小，剧情语言质量有限。昵称是虚构记忆分区，不是身份认证，只输入虚构信息。验收证据不等同赛事正式分数，正式结果以对应提交任务为准。


HTTPS reverse proxy: loopback and the default Docker host gateway are trusted for forwarded protocol headers. A custom network may set DREAM_TRUSTED_PROXY_IPS to its actual proxy IPs. This preserves same-origin validation for HTTPS; unrelated Origin headers are still rejected.


Direct temporary HTTPS game: https://status-toolbox-kinase-ray.trycloudflare.com . No login/key required; play twice with same nickname to verify actual Dify+PowerContext history. See PREVIEW.md and evidence/https_preview_acceptance.json. This current snapshot is verified with2CPU2GiB128PID and fixes trusted HTTPS proxy protocol recognition; local acceptance does not establish the cause of previous platformfail100.


## Standard Docker Compose entrypoint

From either the repository root or `dify/`, run:

```bash
docker compose up --build
```

Open http://127.0.0.1:8080 after health becomes ready. The named data volume is initialized automatically and preserves Dify and PowerContext data. `DREAM_HTTP_PORT=18121 docker compose up --build` chooses a different loopback port. Resource limits are2CPU,2GiB and128PIDs. No account, external credential or manual DSL rebinding is needed. The root and application Compose files build their respective matching Dockerfile contexts. The complete source implementation remains inside `dify/`.

For repeatable fresh-player checks, use a new fictional nickname. To reset all state, stop only this Compose project and remove its named data volume; this removes that game's saved history. First build needs network access to the pinned official images, PyPI, Debian, ModelScope and llama.cpp release asset. The demonstration URL is optional; local deployment operates independently from it.


Build download recovery: model/runtime downloads now have30-second read timeouts, a600-second deadline per asset, up to5 attempts with verified Range resume, and SHA256 plus exact-size validation. Two independent assets download concurrently. Interrupted transfers, a server ignoring Range, wrong checksums, and verified caches were tested using an actual local HTTP server; evidence/download_recovery_test.json records results. The uncached standard Compose attempt stalled at435937280/491400032bytes and was stopped; evidence/previous_download_stall.json records this. Compose runtime acceptance used checksum-verified public asset caches from the preceding complete clean-root build. Caches contain no credentials and are not committed; normal builds download the same pinned assets. This is a real deployment reliability fix and does not establish the platformerror100cause.


Build runtime dependency reuse: the Dockerfile pins the same official Dify1.18.0 image digest and reuses its immutable Python site-packages through a .pth entry in a separate game venv. Dify's environment is not modified. Only aiosqlite0.22.1, sqlite-vec0.1.9, rfc8785=0.1.4, python-multipart0.0.32 and the unmodified checksum-locked PowerContext1.2.0 wheel are added to the game venv. Common dependency versions come from that pinned base image and are recorded by actual runtime inspection. The former full requirements list remains as provenance, not an additional installation step. This removes duplicate package downloads; actual cold workflow and memory integration passed; raw evidence is included, including a harmless English input refused by the small Qwen model.

The full application import is checked during image build, so a missing SDK dependency fails before deployment. Existing Dify model/runtime versions are fixed by the base-image digest. No scoring or evaluator code is changed. Earlier formal failures still have no disclosed backend cause; this deployment simplification does not establish their cause.
