# 阶跃星辰 × seekdb — 一页实测技术报告

> 本报告由浏览器真实运行数据生成，生成时间：2026-10-31T08:37:51.679Z。若 GPU 不可用则不伪造 WebGPU 结果。

## 方法与架构

- **模型**：Xenova/all-MiniLM-L6-v2（Apache-2.0；384维；mean pooling + normalize）。INT8 对应模型仓库 model_quantized.onnx；FP16 对应 model_fp16.onnx；FP32 对应 model.onnx。
- **端侧**：Transformers.js Transformers.js 3.8.1；显式选 WebGPU FP16，出错时自动切换 WASM INT8；文档和查询向量都由浏览器本地计算。
- **数据层**：seekdb-js embedded；384维 HNSW cosine + IK 全文索引。向量/原文/标题/ID 存于 seekdb。调用 collection.hybridSearch，rank: {rrf:{}}，数据库内融合，绝无客户端拼接。
- **写入/刷新**：分批写入后通过真实 hybridSearch 轮询检查新文档是否可见；不同精度、不同知识库单独建集合。
- **固定条件**：16 条文本、8 条查询、topK=3；浏览器 Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0。冷加载与热查询分开，热延迟取第 2 次及后续查询的中位数。
- **模型文件大小**：尽可能用 HTTP HEAD 获取 Content-Length；未拿到则报告缺失；第三方 Hub 标注值仅供参考，不伪称本机实测。文件大小比：3.93×（HTTP HEAD）。

## 量化性能与检索质量

| 配置 | 模型文件 | 向量化吞吐 | seekdb 热查询中位数 | 端到端热查询中位数 | Recall@3 / nDCG@3 |
|---|---:|---:|---:|---:|---:|
| fp32-wasm | 90.39 MB | 22.28 doc/s | 3.9 ms | 293 ms | 0.625 / 0.615 |
| q8-wasm | 22.97 MB | 35.87 doc/s | 4.8 ms | 364 ms | 0.6875 / 0.6633 |

对比 FP32→INT8：吞吐倍率 1.61×；Recall@3 变化 0.0625；nDCG@3 变化 0.0483。

**可用性与降级**：检测到 WebGPU=false；跳过配置：无。

**实验文件**：stepfun/evidence/browser-benchmark-*.json 保存每项查询的原始计时与返回 ID；stepfun/evidence/server-events.jsonl 保存数据库导入、查询和索引可见性日志。

**局限**：基准模型主要面向英文短文，中文 UI 不等于模型多语言能力；小样本结果不能推广为生产性能；浏览器/设备/网络缓存会影响首次加载。
