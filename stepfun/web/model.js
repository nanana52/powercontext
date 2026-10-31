// All embedding inference happens here, in the user's browser.
import { pipeline, env } from '@huggingface/transformers';

export const MODEL = 'Xenova/all-MiniLM-L6-v2';
export const MODEL_FILES = {
  'fp32-wasm': { dtype: 'fp32', device: 'wasm', file: 'model.onnx', hubMB: 90.4 },
  'q8-wasm': { dtype: 'q8', device: 'wasm', file: 'model_quantized.onnx', hubMB: 23.0 },
  'fp16-webgpu': { dtype: 'fp16', device: 'webgpu', file: 'model_fp16.onnx', hubMB: 45.3 },
};
const models = new Map();
// The browser may fetch public model weights, but never sends user text to
// Hugging Face or any external inference endpoint.
env.allowLocalModels = true;
env.localModelPath = "/models/";
env.allowRemoteModels = false;

export async function canUseWebGPU() {
  if (!navigator.gpu || !window.isSecureContext) return false;
  try { return Boolean(await navigator.gpu.requestAdapter()); } catch { return false; }
}

export async function getModel(wanted = 'auto', onProgress = () => {}) {
  const candidates = wanted === 'auto'
    ? (await canUseWebGPU() ? ['fp16-webgpu', 'q8-wasm'] : ['q8-wasm'])
    : [wanted];
  let failure = null;
  for (const mode of candidates) {
    const options = MODEL_FILES[mode];
    if (!options) throw new Error(`未知推理模式：${mode}`);
    if (mode === 'fp16-webgpu' && !(await canUseWebGPU())) {
      failure = new Error('WebGPU 不可用');
      onProgress('本机 WebGPU 不可用，使用 WASM');
      continue;
    }
    if (models.has(mode)) return { ...models.get(mode), cached: true, loadMs: 0 };
    const started = performance.now();
    try {
      onProgress(`加载 ${options.dtype.toUpperCase()} · ${options.device.toUpperCase()} 模型（首次下载可能较久）`);
      const extractor = await pipeline('feature-extraction', MODEL, {
        device: options.device === 'webgpu' ? 'webgpu' : 'wasm',
        dtype: options.dtype,
        progress_callback: e => {
          if (e.status === 'progress' && Number.isFinite(e.progress)) {
            onProgress(`模型下载 ${Math.floor(e.progress)}% · ${e.file || options.file}`);
          }
        }
      });
      // Warm-up proves the selected backend actually executes on this device.
      const probe = await extractor(['device-side embedding warmup'], { pooling: 'mean', normalize: true });
      if (probe.tolist()[0].length !== 384) throw new Error('模型输出不是 384 维');
      const model = { mode, options, extractor, cached: false,
        loadMs: +(performance.now() - started).toFixed(1) };
      models.set(mode, model);
      onProgress(`已就绪：${options.device.toUpperCase()} / ${options.dtype.toUpperCase()}`);
      return model;
    } catch (error) {
      failure = error;
      onProgress(`${mode} 加载失败：${error.message}`);
      if (wanted !== 'auto') break;
    }
  }
  throw failure || new Error('没有可用的端侧推理后端');
}

export async function embedTexts(model, texts, { batchSize = 8, onProgress = () => {} } = {}) {
  if (!Array.isArray(texts) || !texts.length) throw new Error('没有可编码的文本');
  const size = Math.max(1, Math.min(16, Number(batchSize) || 8));
  const t = performance.now();
  const vectors = [];
  for (let i = 0; i < texts.length; i += size) {
    const chunk = texts.slice(i, i + size);
    const tensor = await model.extractor(chunk, { pooling: 'mean', normalize: true });
    for (const v of tensor.tolist()) {
      if (!Array.isArray(v) || v.length !== 384) throw new Error('embedding 输出维度异常');
      vectors.push(v);
    }
    onProgress(`浏览器向量化 ${Math.min(i + size, texts.length)} / ${texts.length}`);
  }
  return { vectors, embeddingMs: +(performance.now() - t).toFixed(1), batchSize: size };
}

export async function probeModelFileSize(mode) {
  const item = MODEL_FILES[mode];
  const url = `/models/${MODEL}/onnx/${item.file}`;
  try {
    const response = await fetch(url, { method: 'HEAD', cache: 'no-store' });
    const bytes = Number(response.headers.get('content-length'));
    if (response.ok && bytes > 0) return { bytes, mb: +(bytes / 1e6).toFixed(2), source: 'HTTP HEAD Content-Length', url };
  } catch { /* cross-origin may disallow HEAD */ }
  return { bytes: null, mb: null, source: '无法自动测得，仓库标注参考值见 hubReferenceMB', hubReferenceMB: item.hubMB, url };
}
