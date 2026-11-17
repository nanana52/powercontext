# 梦境失物招领局

一款会延续上次剧情的文字游戏：填写虚构昵称、失物与行动，柜员给出故事和下一步选择。使用同一昵称再次登记，会读取以前的记录并接着回应。

Dify 1.18.0 编排整个流程：清洗输入 → 创建玩家分区 → PowerContext 读取历史 → 调用真实本地 Qwen → 保存记忆 → 核实输出。PowerContext 1.2.0 使用官方 Memory 与全文检索保存、复用历史。本作品选择 Dify + PowerContext。

## 提交材料

- app.yml：唯一完整 Dify Workflow DSL。
- backend/：配套服务与固定依赖；真实 Qwen 生成、真实 PowerContext 记忆。
- scripts/：独立 Dify 部署、固定 SDK 下载及自动两轮验收。
- deployment/：精简运行配置，每次部署生成私有密码，网络按项目隔离。
- evidence/acceptance.json、turn1.json、turn2.json：本次从空数据库部署并导入发布后的真实运行结果。
- demo/：可选游戏网页，调用实际已发布 Dify API，应用密钥保留服务端。

## 完整运行与验收

Linux x86_64、Python 3.12（含 venv）、Bash、curl、Docker Engine 与 Compose v2，在本目录执行：

```bash
DREAM_PYTHON=/path/to/python3.12 bash run.sh
```

首次安装需要下载 Python 依赖、Qwen 模型、llama.cpp 和 Dify 镜像，网络耗时与模型下载约500MB需提前预留。模型和 SDK 均校验 SHA256。成功标志为 DIFY_FULL_STACK_ACCEPTANCE_PASS。私有密码与记忆只写入 .runtime，不提交。

默认 Dify 页面端口18080、配套服务18090、模型18081。可用 DREAM_DIFY_PROJECT、DREAM_DIFY_HTTP_PORT、DREAM_DIFY_API_PORT、DREAM_DIFY_WEB_PORT、DREAM_BACKEND_PORT、DREAM_MODEL_PORT 更换项目名和端口。多个部署的数据库、密码及 Docker 网络相互独立。

## 已有 Dify 时导入

执行 bash start_backend.sh；将 app.yml 导入 Dify 1.18.0，设置 POWERCONTEXT_BASE_URL 为 Dify 可达的后端地址，并将 .runtime/access.token 填入秘密变量 POWERCONTEXT_TOKEN。Linux 默认 Docker 网关示例为 http://172.17.0.1:18090。仅放行实际私网地址后发布 Workflow。

## 验证样例

初始条件：从未用过的虚构昵称。第一轮失物“会说话的蓝雨伞”，行动“给雨伞写一封道歉信”，预期 previous_memory_loaded=否、memory_saved=是。第二轮保留昵称，行动“询问柜员上次登记了什么”，预期读取并提及上次记录，previous_memory_loaded=是、memory_saved=是。PowerContext 实际读回2条记录，revision=2。新的昵称没有旧记录；保留 .runtime 后重启可继续读取历史。

## 容器与体验入口

Dockerfile 构建的是配套后端，默认同时启动真实 Qwen 与 PowerContext，前台运行，UID10001、数据/data，端口18090。完整 Dify 编排由上述 bash run.sh 启动。容器镜像构建及离线启动已在前序同源码后端验证。

临时游戏：https://cio-legendary-bent-comfortable.trycloudflare.com 。该地址仅在当前验收进程运行时有效；提交的源码可独立部署。网页通过真实 Dify Workflow 工作，不在前端存放密钥。

Qwen模型较小，语言表现有限；昵称是虚构剧情的记忆分区，不是身份认证。只提交虚构游戏信息。正式评分以赛事平台结果为准。
