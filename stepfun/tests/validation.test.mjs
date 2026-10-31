import test from 'node:test';
import assert from 'node:assert/strict';
import { safeKb, collectionName, validateVector, validateDocuments, validateSearch, keywordFromQuery, normalizeResults } from '../server/validation.mjs';
const vec = Array(384).fill(0.02);
test('namespaces isolate modes and knowledge bases', () => {
  assert.equal(collectionName('demo', 'q8-wasm'), 'sf_demo_q8_wasm');
  assert.notEqual(collectionName('demo', 'q8-wasm'), collectionName('demo', 'fp32-wasm'));
  assert.throws(() => safeKb('../demo'));
});
test('reject fabricated or malformed vectors', () => {
  assert.equal(validateVector(vec).length, 384);
  assert.throws(() => validateVector(Array(2).fill(0)));
  assert.throws(() => validateVector([...vec.slice(0,383), NaN]));
});
test('validate whole client-supplied embedding batch', () => {
  const payload = [{ id:'test_one', title:'Test', text:'Actual document', embedding:vec }];
  assert.equal(validateDocuments(payload)[0].title,'Test');
  assert.throws(() => validateDocuments([...payload, ...payload]));
  assert.equal(validateSearch({text:'hybrid database',embedding:vec,nResults:5}).nResults,5);
});
test('hybrid query text token and result layout', () => {
  assert.equal(keywordFromQuery('How does WebGPU accelerate embeddings?'), 'WebGPU');
  assert.equal(normalizeResults({ids:[['a']],documents:[['hello']],metadatas:[[{title:'X'}]]})[0].metadata.title,'X');
});
