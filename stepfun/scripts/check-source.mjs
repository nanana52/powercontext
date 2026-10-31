import fs from 'node:fs';
const client = fs.readFileSync('web/model.js', 'utf8');
const db = fs.readFileSync('server/db.mjs', 'utf8');
const app = fs.readFileSync('web/app.js', 'utf8');
for (const [assertion, ok] of Object.entries({
  'browser model pipeline': client.includes("pipeline('feature-extraction'"),
  'browser WebGPU explicit': client.includes("device: 'webgpu'"),
  'browser WASM explicit': client.includes("device: 'wasm'"),
  'server has no inference model': !db.includes("pipeline('feature-extraction'"),
  'index uses 384 dimensions': db.includes('dimension: 384'),
  'real DB hybrid RRF': db.includes('c.hybridSearch(') && db.includes('rank: { rrf: {} }'),
  'no queryTexts server model': !db.includes('queryTexts:'),
  'browser uploads embeddings': app.includes('embedding: vectors[j]')
})) {
  if (!ok) throw new Error('source assertion failed: ' + assertion);
  console.log('PASS', assertion);
}
console.log('Static checks only; browser + seekdb runtime verification remains mandatory.');
