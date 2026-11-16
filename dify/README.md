# 梦境失物招领局

一个会记住玩家荒诞失物与行动的文字互动游戏。填写同一昵称即可延续以前的登记；每轮有两个行动方向，也允许玩家自由输入。Dify 承担输入处理、调用顺序、错误判断和最终输出，PowerContext 承担持久记忆写入、全文检索及稳定引用，本地 Qwen 模型生成柜员回复。

## 已验证环境

- Linux x86_64，Python 3.12.12；Dify 1.18.0，DSL 0.7.0。
- PowerContext 源码随 `vendor/powercontext/src` 交付，版本及来源见 `PROVENANCE.json`。
- llama.cpp b12248；Qwen2.5-0.5B-Instruct Q4_K_M，Apache-2.0。
- 需要约 2 GB 空闲内存和 1 GB 后端磁盘，Dify 自身资源另计。无需模型 API Key；首次安装需访问 Python 包源、ModelScope 和 GitHub。

## 启动后端

在具备 Bash、curl、Python 和 pip 的 Linux x86_64 环境执行 `bash start_backend.sh`。脚本在本目录的 `.runtime` 安装固定依赖、下载并校验模型和推理程序哈希，生成本地随机访问令牌，启动模型及 PowerContext 配套 API。运行 `bash stop_backend.sh` 可以停止本部署启动的进程。

模型仅监听 `127.0.0.1:18081`。配套 API 默认监听端口 18090，所有记忆及剧情接口要求 Bearer 令牌。令牌保存在 `.runtime/access.token`，不随材料提交。不要把整个 `.runtime` 上传到公开仓库。

`Dockerfile` 提供后端容器构建入口；采用容器部署时需设置 `DREAM_ACCESS_TOKEN`、挂载可写 `/data`，并将 `DREAM_MODEL_URL` 指向可访问的真实模型服务。本次端到端验证采用主机后端与同机 Docker Dify。

## 全新部署 Dify

已有 Dify 1.18.0 可以直接进入下一节。没有环境时，先安装 Docker Engine 与 Docker Compose v2，再在本目录运行 `python3 scripts/setup_dify.py`。脚本使用随材料交付的官方部署配置，自动生成本地随机密钥和数据库密码，在独立项目 `dream-lostfound` 启动核心服务；打开 `http://127.0.0.1:18080/install` 创建自己的管理员账号。首次下载镜像需要访问 Docker Hub；网络受限时应为自己的 Docker 配置可用镜像源。

## 配置 Dify

1. 在 Dify 1.18.0 工作室导入 `dsl/dream-lostfound.yml`。只有这一份 DSL，无额外知识库或自定义插件。
2. 环境变量 `POWERCONTEXT_BASE_URL` 填 Dify 实际可访问的后端地址。同机 Linux Docker 的默认网关一般为 `http://172.17.0.1:18090`；网络不同应填实际地址。
3. 将 `.runtime/access.token` 的内容填入秘密变量 `POWERCONTEXT_TOKEN`。
4. Dify 1.18.0 若拒绝访问私网地址，在 API、Worker、SSRF Proxy 的环境中设置 `SSRF_PROXY_ALLOW_PRIVATE_IPS=172.17.0.1/32`，仅放行实际配套后端地址，并重建相应容器。不要整体关闭网络保护。
5. 发布应用，从 Dify 的运行界面或 Workflow API 体验。

Dify 工作流的模型步骤通过 HTTP 调用配套服务的 `/v1/story`，实际执行本地 Qwen 推理；没有用固定回复替代模型。本步骤使用 HTTP 节点，因此 Dify 的 `total_tokens` 为 0，不能据此声称没有真实模型调用。模型执行日志在 `.runtime/logs/model.log`。

## 验证样例

用从未使用过的昵称，例如 `梦游测试-当前时间`：

| 轮次 | 失物 | 行动 | 预期表现 |
| --- | --- | --- | --- |
| 第一轮 | 会打喷嚏的雨伞 | 给雨伞递一张纸巾 | 出现首次登记提示，`previous_memory_loaded=否`，`memory_saved=是` |
| 第二轮 | 会打喷嚏的雨伞 | 问柜员我上次带来了什么失物 | 回顾上次雨伞与递纸巾的行动，`previous_memory_loaded=是`，`memory_saved=是` |

随后停止并重启配套后端，再用同一昵称进行第三轮，应仍能读到以前的记录；使用新昵称则从首次登记开始。`evidence/workflow_turn1.json` 与 `workflow_turn2.json` 为实际 Dify Workflow API 结果，分别记录首次无历史和第二轮复用。`evidence/backend_restart.txt` 记录服务重启后真实 Memory 引用仍可读。

## 交付内容与来源

`backend/app.py` 是配套 API 源码；`vendor/powercontext` 包含实际使用的 PowerContext 源码及许可证；`backend/requirements.txt` 固定运行依赖；`PROVENANCE.json` 记录上游修订、模型版本和哈希。该作品延续用户原有《梦境失物招领局》草稿，并修复了请求体、记忆字段、保存确认和运行连接等问题。

模型较小，适合演示，生成内容的丰富程度有限。玩家昵称是游戏记忆的分区标识，不应作为真实身份认证使用；只输入虚构情节。数据存放于 `.runtime/data`，不要求交付任何预置记忆。
