# 依赖与来源

PowerContext 1.2.0 为官方未修改 Apache-2.0 wheel，由 scripts/fetch_dependencies.py 从固定 PyPI 文件地址下载，SHA256 为 9bb55ec13bb2fc1ac84038d917042cc2890ffab4aeedacf1cd5ba5329dcb84b9，许可证在包内。https://pypi.org/project/powercontext/1.2.0/

Dify 1.18.0 使用官方镜像，部署模板从真实已验收配置简化，使用按项目隔离网络和每次随机生成的密码；nginx、squid 配置源于 https://github.com/langgenius/dify/tree/50abea97062110044f15d0e03ccecadd9ccc87ca/docker ，许可 Apache-2.0。

Qwen2.5-0.5B-Instruct-GGUF（Apache-2.0）来自官方 https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF 。llama.cpp b12248 来自 https://github.com/ggml-org/llama.cpp/releases/tag/b12248 。两个运行资源均由源码内的固定 SHA256 校验，不把模型或运行二进制放入参赛目录。
