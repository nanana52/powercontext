import fs from 'node:fs';
import path from 'node:path';
const folder=path.resolve('evidence');
const files=fs.readdirSync(folder).filter(x=>/^browser-benchmark-.*\.json$/.test(x)).sort();
if(!files.length){ console.error('STOP: 尚未运行浏览器真实性能评测。请在网页点击「运行完整实验」。');process.exit(2); }
const file=path.join(folder,files.at(-1));
const d=JSON.parse(fs.readFileSync(file,'utf8'));
const checks={
  'benchmark record source': d.source==='stepfun-browser-benchmark-v1',
  'fixed test set': d.settings?.texts>=8&&d.settings?.queries>=5,
  'FP32 WASM baseline': d.configurations.some(x=>x.variant==='fp32-wasm'&&x.queryDetails?.length>=5),
  'INT8 WASM quantization': d.configurations.some(x=>x.variant==='q8-wasm'&&x.queryDetails?.length>=5),
  'database time recorded': d.configurations.every(x=>x.queryDetails?.every(y=>Number.isFinite(y.seekdbMs))),
  'quality recorded': d.configurations.every(x=>Number.isFinite(x.ndcgAt3)&&Number.isFinite(x.recallAt3)),
  'seekdb call trace': fs.existsSync(path.join(folder,'server-events.jsonl')),
  'technical report generated': fs.existsSync('TECH_ONE_PAGE_RESULTS.md')
};
for(const [name,pass] of Object.entries(checks)) console.log(`${pass?'PASS':'FAIL'} ${name}`);
console.log('Checked evidence:',path.relative(process.cwd(),file));
if(Object.values(checks).some(x=>!x)) process.exitCode=1;
else console.log('Evidence checks pass. Still verify browser fallback behavior and reviewer requirements manually.');
