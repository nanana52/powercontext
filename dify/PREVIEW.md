# 作品临时体验入口

已实测的临时 HTTPS 游戏地址：

https://cio-legendary-bent-comfortable.trycloudflare.com

填写虚构昵称、失物和行动，点击“交给夜班柜员”。保留昵称再输入一次行动，可看到“读取历史：是”“本轮记忆保存：是”。页面请求经真实 Dify Workflow，再由 PowerContext 保存与检索记忆，本地 Qwen 生成文字。

该地址是本次验收期间的临时预览，仅在本机 Dify、模型、游戏与隧道进程运行时有效，不作为永久部署承诺。评审可按 README.md 和 CONTAINER.md 独立部署；私有应用密钥不在源码中。

HTTPS 页面、健康检查及真实工作流调用均已验收，结果见 evidence/https_acceptance.json。
