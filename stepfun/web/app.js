import { MODEL, MODEL_FILES, canUseWebGPU, getModel, embedTexts, probeModelFileSize } from './model.js';
import { median, mean, recallAtK, ndcgAtK } from './evaluation.js';

const $ = id => document.getElementById(id);
const controls = ['sampleBtn', 'uploadBtn', 'searchBtn', 'benchBtn'];
const state = {
  kb: localStorage.getItem('stepfun-kb') || 'demo',
  wanted: localStorage.getItem('stepfun-mode') || 'auto',
  active: null, busy: false, webgpu: false, model: null, report: null
};
function log(message, kind = '') {
  const li = document.createElement('div');
  li.className = `log-entry ${kind}`;
  li.textContent = `${new Date().toLocaleTimeString()}  ${message}`;
  $('log').prepend(li);
  while ($('log').children.length > 36) $('log').lastChild.remove();
  $('statusMessage').textContent = message;
}
function busy(value) {
  state.busy = value;
  for (const id of controls) $(id).disabled = value;
  $('spinner').classList.toggle('spinning', value);
}
function setInfo() {
  $('dbState').textContent = state.dbReady ? 'seekdb · 在线' : 'seekdb · 未连接';
  $('dbState').className = state.dbReady ? 'pill good' : 'pill warn';
  $('gpuState').textContent = state.webgpu ? 'WebGPU · 可检测到' : 'WebGPU · 不可用';
  $('backend').textContent = state.active ? MODEL_FILES[state.active].device.toUpperCase() : '—';
  $('precision').textContent = state.active ? MODEL_FILES[state.active].dtype.toUpperCase() : '—';
}
async function api(route, body = undefined) {
  const config = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const response = await fetch(`/api/${route}`, config);
  const json = await response.json();
  if (!response.ok) throw new Error(json.error || `HTTP ${response.status}`);
  return json;
}
async function refreshStats() {
  if (!state.active) return;
  try {
    const data = await api(`stats?kb=${state.kb}&variant=${state.active}`);
    $('docCount').textContent = data.count;
  } catch (e) { log(`数据库状态：${e.message}`, 'error'); }
}
function updateSelection() {
  const kb = $('kbName').value.trim().toLowerCase();
  if (!/^[a-z][a-z0-9_]{0,23}$/.test(kb)) throw new Error('知识库名称须为小写英文、数字、下划线');
  state.kb = kb;
  state.wanted = $('modeSelect').value;
  localStorage.setItem('stepfun-kb', kb);
  localStorage.setItem('stepfun-mode', state.wanted);
}
async function requireModel(exactMode = null) {
  updateSelection();
  const model = await getModel(exactMode || state.wanted, progress => log(progress));
  if (!exactMode) {
    state.model = model;
    state.active = model.mode;
    setInfo();
    await refreshStats();
  }
  return model;
}
function newId(prefix = 'd') {
  return `${prefix}_${Date.now().toString(36)}_${crypto.randomUUID().replaceAll('-', '').slice(0, 20)}`;
}
async function importDocuments(rows, source = 'user') {
  if (!rows.length) throw new Error('没有可以导入的文档');
  const model = await requireModel();
  let sumWrite = 0, sumRefresh = 0, sumEmbed = 0;
  const started = performance.now();
  // Inference always runs in browser. The Node server receives vectors, never text for model inference.
  for (let i = 0; i < rows.length; i += 16) {
    const group = rows.slice(i, i + 16);
    const { vectors, embeddingMs } = await embedTexts(model, group.map(r => r.text), { batchSize: 8, onProgress: log });
    sumEmbed += embeddingMs;
    const items = group.map((r, j) => ({
      id: r.id || newId('doc'), text: r.text, title: r.title || `文档 ${i+j+1}`,
      source, embedding: vectors[j]
    }));
    const result = await api('import', { kb: state.kb, variant: state.active, items });
    if (!result.indexed) throw new Error('新增文档尚未被索引检索到');
    sumWrite += result.writeMs;
    sumRefresh += result.refreshMs;
    log(`第 ${i+1}～${i+group.length} 条：seekdb 写入 + 索引可见性检查通过`, 'ok');
  }
  $('lastImport').textContent = `${sumEmbed.toFixed(0)} / ${sumWrite.toFixed(0)} / ${sumRefresh.toFixed(0)} ms`;
  $('lastTotal').textContent = `${(performance.now() - started).toFixed(0)} ms`;
  await refreshStats();
  log(`成功：导入 ${rows.length} 段；数据存于 seekdb (${state.kb}/${state.active})`, 'ok');
}
async function runSearch() {
  const query = $('query').value.trim();
  if (query.length < 2) throw new Error('请先输入至少 2 个字符的查询');
  const model = await requireModel();
  const begin = performance.now();
  const { vectors, embeddingMs } = await embedTexts(model, [query], { batchSize: 1, onProgress: log });
  const result = await api('search', { kb: state.kb, variant: state.active, text: query,
    embedding: vectors[0], nResults: 6 });
  const endToEndMs = +(performance.now() - begin).toFixed(1);
  $('queryTiming').textContent = `查询向量化 ${embeddingMs}ms · seekdb ${result.databaseMs}ms · 端到端 ${endToEndMs}ms`;
  const container = $('results');
  container.replaceChildren();
  if (!result.results.length) {
    const p = document.createElement('div'); p.className='empty'; p.textContent='没有查询结果，请先在当前模型精度的知识库中导入文档。'; container.append(p);
  } else {
    for (const item of result.results) {
      const article = document.createElement('article'); article.className = 'result-card';
      const top = document.createElement('div'); top.className='result-top';
      const title = document.createElement('b'); title.textContent = `${String(item.rank).padStart(2, '0')} · ${item.metadata?.title || item.id}`;
      const tag = document.createElement('span'); tag.textContent='seekdb · RRF'; tag.className='tiny-tag';
      const content = document.createElement('p'); content.textContent = item.document;
      const bottom = document.createElement('small'); bottom.textContent = `${item.metadata?.source || 'unknown'}   /   ${item.id}`;
      top.append(title, tag); article.append(top, content, bottom); container.append(article);
    }
  }
  log(`数据库混合检索返回 ${result.results.length} 条（${result.databaseMs} ms）`, 'ok');
}
function splitText(text, title) {
  const paragraphs = text.replaceAll('\r', '').split(/\n\s*\n+/).map(x=>x.trim()).filter(x=>x.length>1);
  const chunks=[]; let index=0;
  for (const p of paragraphs.length ? paragraphs : [text.trim()]) {
    for(let i=0;i<p.length;i+=760) {
      const piece = p.slice(i,i+760);
      if (piece.length > 1) chunks.push({title:`${title} · ${++index}`,text:piece});
    }
  }
  return chunks.slice(0,100);
}
async function sampleRows() {
  const response = await fetch('/fixtures/corpus.json');
  if(!response.ok) throw new Error('未能读取示例语料');
  return response.json();
}
async function exampleAction() {
  await importDocuments((await sampleRows()).map(r=>({ title:r.title, text:r.text })), 'built-in-example');
  $('query').value = 'How does a vector database combine semantic and keyword search?';
}
async function uploadAction() {
  const files = [...$('files').files];
  if (!files.length) throw new Error('请先选择 .txt 或 .md 文件');
  const docs = [];
  for (const file of files.slice(0, 8)) {
    if (!/\.(txt|md)$/i.test(file.name)) throw new Error('仅支持 .txt 或 .md 文本文件');
    docs.push(...splitText(await file.text(), file.name));
  }
  if (docs.length > 160) throw new Error('一次最多导入 160 段，请减少文件');
  await importDocuments(docs, 'file-upload');
}

async function runBenchmark() {
  updateSelection();
  const corpus = await sampleRows();
  const qresp = await fetch('/fixtures/queries.json');
  const queries = await qresp.json();
  const kb = `bench_${Date.now().toString(36)}`;
  const report = {
    source:'stepfun-browser-benchmark-v1', startedAt:new Date().toISOString(),
    environment: { userAgent:navigator.userAgent, webgpuDetected:state.webgpu,
      secureContext:window.isSecureContext, online:navigator.onLine, browserLanguage:navigator.language },
    model:{id:MODEL, dimensions:384, pooling:'mean', normalized:true, runtime:'Transformers.js 3.8.1'},
    settings:{knowledgeBase:kb, texts:corpus.length, queries:queries.length, topK:3,
      eval:'binary Recall@3 and nDCG@3 (fixed relevance judgments)', coldWarm:'first query separated; warm median of remaining queries'},
    configurations:[], skipped:[], completedAt:null
  };
  log('开始固定语料性能实验；所有 embedding 在此浏览器生成。');
  const requested = ['fp32-wasm','q8-wasm', ...(state.webgpu ? ['fp16-webgpu'] : [])];
  for (const variant of requested) {
    log(`评测 ${variant}：加载模型 / 编码 ${corpus.length} 条 / 数据库混合检索`);
    let model;
    try { model = await getModel(variant, log); }
    catch (e) { report.skipped.push({ variant, reason:e.message }); log(`${variant} 不可用：${e.message}`, 'error'); continue; }
    const stage = { variant, dtype:MODEL_FILES[variant].dtype, device:MODEL_FILES[variant].device,
      modelLoadMs:model.loadMs, modelLoadCached:model.cached,
      batchSize:variant==='fp32-wasm'?1:8,
      modelSize:await probeModelFileSize(variant), documentCount:corpus.length,
      queryDetails:[] };
    const {vectors, embeddingMs} = await embedTexts(model, corpus.map(x=>x.text),
      {batchSize:stage.batchSize,onProgress:log});
    stage.documentEmbeddingMs = embeddingMs;
    stage.embeddingThroughputDocsPerSec = +(1000*corpus.length / Math.max(embeddingMs, 1)).toFixed(2);
    stage.writeMs=0; stage.indexVisibilityMs=0;
    const items=corpus.map((d,i)=>({id:`doc_${d.id}`,title:d.title,text:d.text,
      source:'fixed-benchmark',embedding:vectors[i]}));
    for(let i=0;i<items.length;i+=16) {
      const data=await api('import',{kb,variant,items:items.slice(i,i+16)});
      if(!data.indexed) throw new Error('benchmark index refresh verification failed');
      stage.writeMs+=data.writeMs; stage.indexVisibilityMs+=data.refreshMs;
    }
    for (const [idx, query] of queries.entries()) {
      const t=performance.now();
      const emb=await embedTexts(model,[query.text],{batchSize:1});
      const res=await api('search',{kb,variant,text:query.text,embedding:emb.vectors[0],nResults:3});
      const e2e=+(performance.now()-t).toFixed(1);
      const ids=res.results.map(x=>x.id.replace(/^doc_/,''));
      stage.queryDetails.push({queryId:query.id,query:query.text,relevant:query.relevant,
        returnedIds:ids,queryEmbeddingMs:emb.embeddingMs,seekdbMs:res.databaseMs,endToEndMs:e2e,
        recallAt3:recallAtK(ids,query.relevant),ndcgAt3:ndcgAtK(ids,query.relevant),cold:idx===0});
    }
    stage.recallAt3=mean(stage.queryDetails.map(x=>x.recallAt3));
    stage.ndcgAt3=mean(stage.queryDetails.map(x=>x.ndcgAt3));
    stage.firstQueryMs=stage.queryDetails[0]?.endToEndMs ?? null;
    stage.warmMedianSeekdbMs=median(stage.queryDetails.slice(1).map(x=>x.seekdbMs));
    stage.warmMedianE2eMs=median(stage.queryDetails.slice(1).map(x=>x.endToEndMs));
    stage.warmMedianQueryEmbeddingMs=median(stage.queryDetails.slice(1).map(x=>x.queryEmbeddingMs));
    report.configurations.push(stage);
    log(`已测 ${variant}：Recall@3=${stage.recallAt3} · nDCG@3=${stage.ndcgAt3} · 热查询 ${stage.warmMedianE2eMs}ms`,'ok');
    showBenchmark(report);
  }
  if (!report.configurations.length) throw new Error('没有任何可运行的评测配置');
  const base=report.configurations.find(c=>c.variant==='fp32-wasm');
  const optimized=report.configurations.find(c=>c.variant==='q8-wasm');
  report.comparison=(base&&optimized)?{
    throughputSpeedup:+(optimized.embeddingThroughputDocsPerSec/Math.max(base.embeddingThroughputDocsPerSec,.001)).toFixed(2),
    recallDelta:+(optimized.recallAt3-base.recallAt3).toFixed(4),
    ndcgDelta:+(optimized.ndcgAt3-base.ndcgAt3).toFixed(4),
    modelSizeReferenceRatio: +(MODEL_FILES['fp32-wasm'].hubMB / MODEL_FILES['q8-wasm'].hubMB).toFixed(2),
    note:'modelSizeReferenceRatio uses model repository listing; not benchmark device measurements.'
  }:null;
  report.completedAt=new Date().toISOString();
  state.report=report;
  const stored=await api('evidence',{report});
  showBenchmark(report);
  log(`性能与质量实测报告已存储：stepfun/${stored.saved}`,'ok');
}
function showBenchmark(report) {
  const tbody=$('benchRows'); tbody.replaceChildren();
  for (const c of report.configurations) {
    const tr=document.createElement('tr');
    const vals=[c.variant, c.modelSize.mb == null ? '未测得' : `${c.modelSize.mb}MB`,
      `${c.embeddingThroughputDocsPerSec} doc/s`,`${c.warmMedianSeekdbMs}ms`,
      `${c.warmMedianE2eMs}ms`,`${(c.recallAt3*100).toFixed(1)}% / ${c.ndcgAt3}`];
    for (const v of vals) {const td=document.createElement('td'); td.textContent=v; tr.append(td);}
    tbody.append(tr);
  }
  $('benchNote').textContent=report.skipped.length?`跳过：${report.skipped.map(x=>x.variant+'（'+x.reason+'）').join('；')}`:'原始测试会自动写入 stepfun/evidence/；未测得的模型大小不会捏造数值。';
}
function wrap(task) {
  return async ()=>{ if (state.busy) return; busy(true); try {await task();} catch(e){log(e.message||String(e),'error');console.error(e);} finally{busy(false);} };
}

$('kbName').value=state.kb;
$('modeSelect').value=state.wanted;
$('sampleBtn').addEventListener('click',wrap(exampleAction));
$('uploadBtn').addEventListener('click',wrap(uploadAction));
$('searchBtn').addEventListener('click',wrap(runSearch));
$('benchBtn').addEventListener('click',wrap(runBenchmark));
$('kbName').addEventListener('change',()=>{try{updateSelection();state.active=null;setInfo();$('docCount').textContent='—';log('知识库已切换，原库数据不会丢失。');}catch(e){log(e.message,'error');}});
$('modeSelect').addEventListener('change',()=>{try{updateSelection();state.active=null;setInfo();$('docCount').textContent='—';log('模型模式已切换：不同精度数据各存独立 seekdb 集合。');}catch(e){log(e.message,'error');}});
$('downloadBtn').addEventListener('click',()=>{
  if(!state.report) {log('请先运行真实评测后再导出。','error');return;}
  const url=URL.createObjectURL(new Blob([JSON.stringify(state.report,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='stepfun-benchmark.json';a.click();URL.revokeObjectURL(url);
});
(async()=>{
  state.webgpu=await canUseWebGPU();
  setInfo();
  try {
    await api('health');state.dbReady=true;setInfo();
    log('seekdb 已连接。点击「导入演示语料」开始浏览器端向量化。','ok');
  }catch(e){state.dbReady=false;setInfo();log('seekdb 连接失败，请查看 VS Code 终端：'+e.message,'error');}
})();
