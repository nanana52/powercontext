# StepFun × seekdb — 一页技术说明（实测版）

**作品**：Fieldnotes 端侧迷你知识库；**赛题**：端侧 AI 推理性能优化与 seekdb 混合检索。**环境**：浏览器本地向量化 + Node.js 服务 + Docker seekdb Server（127.0.0.1:2881，`test` 数据库）。

**数据流程**：浏览器导入 `.txt/.md` 或 16 条固定演示语料，使用 `@huggingface/transformers@3.8.1` / ONNX Runtime Web 计算 384 维 mean-pooled、归一化 embedding。浏览器连同原文、ID、标题和来源元数据传给 Node 后端；Node 不进行模型推理。seekdb-js 的 `collection.add()` 保存全部数据，全文索引与 HNSW 余弦向量索引由 seekdb 管理；写入后通过 `hybridSearch` 检查索引可见性。查询同样在浏览器向量化，服务端调用 seekdb 的 `hybridSearch({query,knn,rank:{rrf:{}}})` 做数据库内融合排序；不在客户端拼接检索结果。

**模型与降级**：开源模型 `Xenova/all-MiniLM-L6-v2`（Apache-2.0）；FP32 `model.onnx`、INT8/Q8 `model_quantized.onnx`、FP16 `model_fp16.onnx` 均从公开仓库下载到站点静态文件目录，由浏览器从同源 `/models/` 加载。浏览器支持 WebGPU 时优先尝试 FP16/WebGPU，失败降至 Q8/WASM；WASM 路径已实际验证，本次环境未能实测 WebGPU。无云端推理 API。

**实测**：固定 16 文档、8 查询，报告 `evidence/browser-benchmark-2026-10-31T08-37-51-740Z.json`（原始逐查询数据，2026-10-31）。模型大小指 ONNX 单文件，不含其他模型资产。

| 配置 | ONNX 大小 | 向量化吞吐 | seekdb 热查询 | 端到端热查询 | Recall@3 | nDCG@3 |
|---|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 90.39 MB | 22.28 doc/s | 3.9 ms | 293 ms | 62.5% | 0.615 |
| INT8(Q8) / WASM | 22.97 MB | 35.87 doc/s | 4.8 ms | 364 ms | 68.8% | 0.6633 |

**解读**：ONNX 文件压缩比为 90.39/22.97≈3.93×；向量化吞吐约提高 61%，本轮测试集上 Recall@3 与 nDCG@3 未下降，但 Q8 端到端查询从 293ms 增至 364ms。FP32 baseline 使用 batch=1，Q8 优化使用 batch=8，吞吐改善同时包含批处理的贡献；不能单独归因于量化。未实测的 GPU 和硬件参数不补造。

**状态、复现、安全**：知识库与精度使用隔离集合；索引刷新/新增文档可见性由实际数据库查询验证。Docker 持久化数据保存在独立 volume，数据库密码在 `$HOME/.config/stepfun/seekdb.env` 而非源码。复现：`npm ci --legacy-peer-deps`，依次运行 `scripts/01_seekdb_docker.sh`、`scripts/02_download_models.sh`、`scripts/03_start_site.sh`，随后在 Chrome/Edge 打开 5173；运行 `npm run check && npm run acceptance && npm run build`。Docker 镜像用于测试，不作为生产环境安全部署建议。

**引用**：https://github.com/oceanbase/seekdb-js · https://github.com/oceanbase/docker-images/blob/main/seekdb/README.md · https://huggingface.co/Xenova/all-MiniLM-L6-v2
