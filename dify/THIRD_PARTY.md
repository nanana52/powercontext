# Dependency provenance

Dify1.18.0 officialAPI image sha256:0120970fb4ea59aa328d63b7dda635cccc071efb8aae470cd07115a026dbffd3, Apache-2.0, https://github.com/langgenius/dify . ActualDify engine andPostgreSQL persisted workflows run inside container.

PowerContext1.2.0 official unmodified PyPI wheel, Apache-2.0. SHA2569bb55ec13bb2fc1ac84038d917042cc2890ffab4aeedacf1cd5ba5329dcb84b9. https://pypi.org/project/powercontext/1.2.0/ . License inside original wheel. SDK in isolated venv.

Qwen2.5-0.5B-Instruct-GGUF, Apache-2.0, https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF . llama.cpp b12248 https://github.com/ggml-org/llama.cpp/releases/tag/b12248 . Both fixedSHA256 in source; binaries not committed.

PostgreSQL15.20-0+deb12u1 andRedis5:7.0.15-1~deb12u10 fromDebian12 official packages; licenses included in image. UTF8/C.UTF-8 data initialization.
