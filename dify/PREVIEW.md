# 直接体验与验收

当前临时 HTTPS 游戏入口：

https://status-toolbox-kinase-ray.trycloudflare.com

无需登录或配置密钥。使用一个新虚构昵称，输入“会说话的蓝雨伞”和“给雨伞写信”，点击按钮；保留昵称再输入“回顾我上次登记的事情”。第二轮应显示已读取历史、记忆保存成功，并提及上次失物和行动。

该入口运行提交的真实 Dify 工作流、PowerContext 和本地 Qwen。HTTP API 回传实际 workflow_run_id。外网健康检查、带 Origin 的两轮真实互动以及错误 Origin 的403校验均已执行，记录见 evidence/https_preview_acceptance.json。

这是临时验收入口，只在当前进程运行时有效；源码支持通过 Dockerfile 和 run.sh 独立部署，不依赖该地址。模型不需要外部服务密钥；首次镜像构建需要联网下载校验过的固定依赖和模型。

此次修复：Uvicorn 在可信本机及默认Docker网关转发时识别 HTTPS 协议，避免正确同源请求误报403。使用自定义 Docker 网络或不同反向代理时，用 DREAM_TRUSTED_PROXY_IPS 指定真实代理IP；不相关来源仍拒绝。
