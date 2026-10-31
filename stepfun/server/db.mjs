// The only vector and text retrieval engine is seekdb. No app-layer fusion.
import path from 'node:path';
import fs from 'node:fs';
import { performance } from 'node:perf_hooks';
import { SeekdbClient, Schema, FulltextIndexConfig, VectorIndexConfig } from 'seekdb';
import { collectionName, keywordFromQuery, normalizeResults } from './validation.mjs';

const directory = path.resolve(process.cwd(), '.data/seekdb');
fs.mkdirSync(path.dirname(directory), { recursive: true });
let db = null;
const collections = new Map();

function client() {
  if (!db) db = new SeekdbClient({
    host: '127.0.0.1',
    port: 2881,
    user: 'root',
    password: process.env.SEEKDB_PASSWORD,
    database: 'test'
  });
  return db;
}

export async function getCollection(kb, variant) {
  const name = collectionName(kb, variant);
  if (collections.has(name)) return collections.get(name);
  // Explicit full-text index and HNSW dense-vector index. No Node embedding
  // function is installed: all 384 dimensions originate in browser WebGPU/WASM.
  const schema = new Schema()
    .createIndex(new FulltextIndexConfig('ik', { ik_mode: 'smart' }))
    .createIndex(new VectorIndexConfig({
      hnsw: { dimension: 384, distance: 'cosine' },
      embeddingFunction: null
    }));
  const created = await client().getOrCreateCollection({ name, schema });
  collections.set(name, created);
  return created;
}

export async function ping() {
  const t = performance.now();
  await getCollection('demo', 'q8-wasm');
  return { database: 'seekdb server', ready: true,
    connectionMs: Number((performance.now() - t).toFixed(1)) };
}

export async function importBatch(kb, variant, items) {
  const c = await getCollection(kb, variant);
  const t = performance.now();
  await c.add({
    ids: items.map(x => x.id), documents: items.map(x => x.text),
    metadatas: items.map(x => ({ title: x.title, source: x.source, dtype: variant, kb })),
    embeddings: items.map(x => x.embedding)
  });
  const writeMs = performance.now() - t;
  // seekdb manages index maintenance. Do not claim refresh completion until
  // an actual hybrid search sees one of the newly added IDs.
  const needle = items[items.length - 1];
  const start = performance.now();
  let verified = false;
  let attempts = 0;
  let lastError = null;
  while (performance.now() - start < 16000 && !verified) {
    attempts++;
    try {
      const rs = await c.hybridSearch({
        query: { whereDocument: { $contains: keywordFromQuery(needle.text) }, nResults: 50 },
        knn: { queryEmbeddings: [needle.embedding], nResults: 50 },
        rank: { rrf: {} }, nResults: 50, include: ['documents', 'metadatas']
      });
      verified = normalizeResults(rs).some(r => r.id === needle.id);
    } catch (e) { lastError = e.message; }
    if (!verified) await new Promise(r => setTimeout(r, 320));
  }
  const refreshMs = performance.now() - start;
  return { count: items.length, writeMs: +writeMs.toFixed(1), refreshMs: +refreshMs.toFixed(1),
    indexed: verified, refreshAttempts: attempts, indexError: verified ? null : lastError,
    collection: collectionName(kb, variant) };
}

export async function hybridSearch(kb, variant, text, embedding, nResults) {
  const c = await getCollection(kb, variant);
  const t = performance.now();
  const query = {
    query: { whereDocument: { $contains: keywordFromQuery(text) }, nResults: Math.max(30, nResults * 5) },
    knn: { queryEmbeddings: [embedding], nResults: Math.max(30, nResults * 5) },
    rank: { rrf: {} }, nResults, include: ['documents', 'metadatas']
  };
  const results = await c.hybridSearch(query);
  return { results: normalizeResults(results), databaseMs: +(performance.now() - t).toFixed(1),
    collection: collectionName(kb, variant), mode: 'seekdb.hybridSearch / RRF',
    keyword: keywordFromQuery(text) };
}

export async function collectionStats(kb, variant) {
  const c = await getCollection(kb, variant);
  const count = await c.count();
  return { collection: collectionName(kb, variant), count, variant, kb };
}

export async function shutdown() {
  if (db) await db.close();
  db = null;
}
