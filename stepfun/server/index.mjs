import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { createServer as createViteServer } from 'vite';
import { ping, importBatch, hybridSearch, collectionStats, shutdown } from './db.mjs';
import { safeKb, safeVariant, validateDocuments, validateSearch } from './validation.mjs';
import { renderReport } from './report.mjs';

const app = express();
const PORT = Number(process.env.PORT || 5173);
app.disable('x-powered-by');
app.use(express.json({ limit: '3mb' }));
const evidenceDir = path.resolve(process.cwd(), 'evidence');
fs.mkdirSync(evidenceDir, { recursive: true });
function logEvent(action, payload) {
  const line = JSON.stringify({ at: new Date().toISOString(), action, ...payload }) + '\n';
  fs.appendFileSync(path.join(evidenceDir, 'server-events.jsonl'), line);
}
const handle = fn => async (req, res) => {
  try { res.json(await fn(req)); }
  catch (e) { console.error('[seekdb]', e); res.status(422).json({ error: String(e.message || e) }); }
};

app.get('/api/health', handle(async () => await ping()));
app.get('/api/stats', handle(async req => collectionStats(safeKb(req.query.kb || 'demo'), safeVariant(req.query.variant || 'q8-wasm'))));
app.post('/api/import', handle(async req => {
  const kb = safeKb(req.body.kb);
  const variant = safeVariant(req.body.variant);
  const items = validateDocuments(req.body.items);
  const t = performance.now();
  const result = await importBatch(kb, variant, items);
  logEvent('import', { kb, variant, documentIds: items.map(x => x.id), count: items.length, ...result,
    totalMs: +(performance.now() - t).toFixed(1) });
  if (!result.indexed) throw new Error('索引刷新/可见性验证尚未成功：' + (result.indexError || '请检查数据库日志'));
  return result;
}));
app.post('/api/search', handle(async req => {
  const kb = safeKb(req.body.kb);
  const variant = safeVariant(req.body.variant);
  const { text, embedding, nResults } = validateSearch(req.body);
  const result = await hybridSearch(kb, variant, text, embedding, nResults);
  logEvent('hybrid_search', { kb, variant, query: text, keyword: result.keyword,
    ids: result.results.map(x => x.id), databaseMs: result.databaseMs, mode: result.mode });
  return result;
}));
app.post('/api/evidence', handle(async req => {
  const { report } = req.body || {};
  if (!report || report.source !== 'stepfun-browser-benchmark-v1' || !Array.isArray(report.configurations)) {
    throw new Error('只能保存应用真实产生的测试报告');
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const name = `browser-benchmark-${stamp}.json`;
  fs.writeFileSync(path.join(evidenceDir, name), JSON.stringify(report, null, 2), { flag: 'wx' });
  fs.writeFileSync(path.resolve(process.cwd(), 'TECH_ONE_PAGE_RESULTS.md'), renderReport(report));
  return { saved: `evidence/${name}` };
}));

const vite = await createViteServer({ server: { middlewareMode: true, host: '0.0.0.0' }, appType: 'spa' });
app.use(vite.middlewares);
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`\nStepfun / local inference × seekdb: http://localhost:${PORT}`);
  console.log('All embeddings computed in browser; seekdb stores & hybrid-searches vectors.\n');
});
const close = async () => {
  server.close();
  await vite.close();
  await shutdown();
  process.exit(0);
};
process.once('SIGINT', close);
process.once('SIGTERM', close);
