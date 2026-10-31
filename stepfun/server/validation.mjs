export const DIMENSION = 384;
export const MAX_BATCH = 32;
const VARIANTS = new Set(['fp32-wasm', 'q8-wasm', 'fp16-webgpu']);

export function safeKb(value) {
  if (typeof value !== 'string' || !/^[a-z][a-z0-9_]{0,23}$/.test(value)) {
    throw new Error('知识库名称只能包含小写字母、数字、下划线，并以字母开头（最长 24 字符）');
  }
  return value;
}
export function safeVariant(value) {
  if (!VARIANTS.has(value)) throw new Error('未知模型模式：' + String(value));
  return value;
}
export function collectionName(kb, variant) {
  return `sf_${safeKb(kb)}_${safeVariant(variant).replace(/-/g, '_')}`;
}
export function validateVector(v) {
  if (!Array.isArray(v) || v.length !== DIMENSION || !v.every(n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 1.01)) {
    throw new Error('必须上传浏览器计算的 384 维有限归一化向量');
  }
  return v;
}
export function validateDocuments(items) {
  if (!Array.isArray(items) || items.length < 1 || items.length > MAX_BATCH) throw new Error(`每批导入 1～${MAX_BATCH} 条`);
  const seen = new Set();
  return items.map(item => {
    if (!item || typeof item.id !== 'string' || !/^[a-zA-Z0-9_-]{1,96}$/.test(item.id)) throw new Error('文档 ID 不合法');
    if (seen.has(item.id)) throw new Error('同一批次出现重复 ID');
    seen.add(item.id);
    if (typeof item.text !== 'string' || item.text.length < 2 || item.text.length > 5000) throw new Error('每段文档限 2～5000 字符');
    if (typeof item.title !== 'string' || !item.title || item.title.length > 160) throw new Error('文档标题不合法');
    return { id: item.id, title: item.title, text: item.text, source: String(item.source || 'upload').slice(0, 100), embedding: validateVector(item.embedding) };
  });
}
export function validateSearch({ text, embedding, nResults }) {
  if (typeof text !== 'string' || text.trim().length < 2 || text.length > 250) throw new Error('查询文字限 2～250 字符');
  const limit = Number(nResults ?? 5);
  if (!Number.isInteger(limit) || limit < 1 || limit > 20) throw new Error('结果数限 1～20');
  return { text: text.trim(), embedding: validateVector(embedding), nResults: limit };
}
export function keywordFromQuery(text) {
  const tokens = text.trim().match(/[A-Za-z][A-Za-z0-9_-]{2,}|[\u3400-\u9fff]{2,}/g) || [];
  const stop = new Set(['how','does','the','and','what','when','where','why','with','about','which','from','that','into','must','still','using','could','should','their','there','this','would','have','are','can','for','then']);
  return (tokens.find(s => s.length > 3 && !stop.has(s.toLowerCase())) || tokens[0] || text.trim().slice(0, 16)).slice(0, 50);
}
export function normalizeResults(result) {
  const flatten = v => Array.isArray(v?.[0]) ? v[0] : (v || []);
  const ids = flatten(result?.ids);
  const documents = flatten(result?.documents);
  const metadatas = flatten(result?.metadatas);
  const distances = flatten(result?.distances);
  return ids.map((id, i) => ({
    id: String(id), document: String(documents[i] || ''),
    metadata: metadatas[i] || {}, distance: distances[i] ?? null,
    rank: i + 1
  }));
}
