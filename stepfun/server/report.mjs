// Generate the one-page results table only from recorded browser measurements.
const n = v => v === null || v === undefined ? '未测得' : String(v);
const size = c => c.modelSize?.mb == null ? '未测得（见仓库参考值）' : `${c.modelSize.mb} MB`;
export function renderReport(report) {
  const rows = report.configurations.map(c =>
    `| ${c.variant} | ${size(c)} | ${n(c.embeddingThroughputDocsPerSec)} doc/s | ${n(c.warmMedianSeekdbMs)} ms | ${n(c.warmMedianE2eMs)} ms | ${n(c.recallAt3)} / ${n(c.ndcgAt3)} |`
  ).join('\n');
  const base = report.configurations.find(x => x.variant === 'fp32-wasm');
  const q8 = report.configurations.find(x => x.variant === 'q8-wasm');
  const ratio = base?.modelSize?.bytes && q8?.modelSize?.bytes
    ? (base.modelSize.bytes / q8.modelSize.bytes).toFixed(2) + '×（HTTP HEAD）'
    : '尚未自动测得；模型仓库标注 FP32≈90.4 MB、INT8≈23.0 MB，参考压缩比≈3.93×';
  return `# 阶跃星辰 × seekdb — 一页实测技术报告\n\n`+
    `> 本报告由浏览器真实运行数据生成，生成时间：${report.completedAt}。若 GPU 不可用则不伪造 WebGPU 结果。\n\n`+
    `## 方法与架构\n\n`+
    `- **模型**：${report.model.id}（Apache-2.0；384维；mean pooling + normalize）。INT8 对应模型仓库 model_quantized.onnx；FP16 对应 model_fp16.onnx；FP32 对应 model.onnx。\n`+
    `- **端侧**：Transformers.js ${report.model.runtime}；显式选 WebGPU FP16，出错时自动切换 WASM INT8；文档和查询向量都由浏览器本地计算。\n`+
    `- **数据层**：seekdb-js embedded；384维 HNSW cosine + IK 全文索引。向量/原文/标题/ID 存于 seekdb。调用 collection.hybridSearch，rank: {rrf:{}}，数据库内融合，绝无客户端拼接。\n`+
    `- **写入/刷新**：分批写入后通过真实 hybridSearch 轮询检查新文档是否可见；不同精度、不同知识库单独建集合。\n`+
    `- **固定条件**：${report.settings.texts} 条文本、${report.settings.queries} 条查询、topK=${report.settings.topK}；浏览器 ${report.environment.userAgent}。冷加载与热查询分开，热延迟取第 2 次及后续查询的中位数。\n`+
    `- **模型文件大小**：尽可能用 HTTP HEAD 获取 Content-Length；未拿到则报告缺失；第三方 Hub 标注值仅供参考，不伪称本机实测。文件大小比：${ratio}。\n\n`+
    `## 量化性能与检索质量\n\n`+
    `| 配置 | 模型文件 | 向量化吞吐 | seekdb 热查询中位数 | 端到端热查询中位数 | Recall@3 / nDCG@3 |\n`+
    `|---|---:|---:|---:|---:|---:|\n${rows}\n\n`+
    `对比 FP32→INT8：吞吐倍率 ${n(report.comparison?.throughputSpeedup)}×；Recall@3 变化 ${n(report.comparison?.recallDelta)}；nDCG@3 变化 ${n(report.comparison?.ndcgDelta)}。\n\n`+
    `**可用性与降级**：检测到 WebGPU=${report.environment.webgpuDetected}；跳过配置：${report.skipped.length ? report.skipped.map(x => x.variant+': '+x.reason).join('；') : '无'}。\n\n`+
    `**实验文件**：stepfun/evidence/browser-benchmark-*.json 保存每项查询的原始计时与返回 ID；stepfun/evidence/server-events.jsonl 保存数据库导入、查询和索引可见性日志。\n\n`+
    `**局限**：基准模型主要面向英文短文，中文 UI 不等于模型多语言能力；小样本结果不能推广为生产性能；浏览器/设备/网络缓存会影响首次加载。\n`;
}
