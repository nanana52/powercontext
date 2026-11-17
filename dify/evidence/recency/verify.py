from pathlib import Path
import subprocess,os,json,time,shutil
b=Path('/opt/oceanbase_completion_20261116');p=b/'dify_recency_fixed_20261118';p.mkdir(exist_ok=False)
source=Path('/mnt/f/\u7814\u7a76\u751f/\u6570\u636e\u5e93/completion_20261116/work/dify_recency_candidate/dify/backend/app.py')
shutil.copyfile(source,p/'app.py')
(p/'Dockerfile').write_text("FROM dream-dify-exact-uncached:20261118\nCOPY app.py /opt/dream/backend/app.py\n")
env=dict(os.environ,DOCKER_HOST='unix://'+str(b/'docker/docker.sock'))
with (p/'build.log').open('wb') as out:
 r=subprocess.run(['docker','build','-t','dream-dify-recency-fixed:20261118','.'],env=env,cwd=p,stdout=out,stderr=out)
assert r.returncode==0
# Direct SDK regression deliberately makes the old first entry shorter/higher-FTS-ranked.
sdk=r"""
import app,asyncio,json
from pathlib import Path
async def run():
 async with app.lifespan(app.app):
  auth='Bearer local-test-placeholder';scope='latest-choice'
  for item,action,size in [('first_umbrella','first_move',1),('second_clock','second_move',100),('third_hat','third_move',20)]:
   text='lostfoundledger\n\u5931\u7269:'+item+'\n\u884c\u52a8:'+action+'\n\u5267\u60c5:'+'story '*size
   await app.remember(app.RememberRequest(scope_id=scope,text=text),auth)
  got=await app.prepare(app.RecallRequest(scope_id=scope),auth)
  assert got['memories'][0]['text'].splitlines()[1]=='\u5931\u7269:third_hat'
  assert got['memories'][1]['text'].splitlines()[1]=='\u5931\u7269:second_clock'
  other=await app.prepare(app.RecallRequest(scope_id='different-player'),auth)
  assert not other['previous_memory_loaded'] and other['context']==''
  prepared=app.WorkflowPrepared(scope_id=scope,player='SDK',item='fourth_book',move='fourth_move',history=got['context'],previous_memory_loaded=True)
  fake_rendered='RENDERED_OLD_HISTORY:'+got['context']
  await app.workflow_save(app.SaveInput(generated=app.GeneratedTurn(prepared=prepared,text=fake_rendered)),auth)
  final=await app.prepare(app.RecallRequest(scope_id=scope),auth)
  saved=final['memories'][0]['text']
  assert saved=='lostfoundledger\n\u5931\u7269:fourth_book\n\u884c\u52a8:fourth_move'
  explicit=await app.prepare(app.RecallRequest(scope_id=scope,query='fourth_book'),auth)
  assert explicit['previous_memory_loaded']
  result={'status':'PASS','latest_history_items':[v['text'].splitlines()[1] for v in final['memories']],'saved_bytes':len(saved.encode()),'old_nested_reply_not_resaved':True,'different_player_empty':True,'explicit_FTS_query':'PASS','actual_PowerContext':'1.2.0'}
  print(json.dumps(result))
asyncio.run(run())
"""
r=subprocess.run(['docker','run','--rm','--network=none','--cpus','1','--memory','512m','--pids-limit','64','-e','DREAM_ACCESS_TOKEN=local-test-placeholder','-e','DREAM_DATA_DIR=/tmp/dream-memory-regression','-e','PYTHONPATH=/opt/dream/backend','--entrypoint','/opt/dream-venv/bin/python','-i','dream-dify-recency-fixed:20261118','-'],env=env,input=sdk.encode(),capture_output=True,timeout=90)
(p/'sdk_regression.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,r.stderr[-1200:]
(p/'sdk_regression.json').write_text(json.dumps(json.loads(r.stdout.splitlines()[-1]),indent=2));print('REAL_SDK_CHRONOLOGY_ISOLATION_NO_RECURSIVE_SAVE_PASS',flush=True)
name='dream-dify-recency-fixed-20261118';data=p/'fresh_data';data.mkdir()
cmd=['docker','run','-d','--name',name,'--network=none','--cpus','2','--memory','2g','--memory-swap','2g','--pids-limit','128','-v',str(data)+':/data','dream-dify-recency-fixed:20261118']
subprocess.run(cmd,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
inner=r"""
import urllib.request,json,time
from pathlib import Path
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def wait():
 for _ in range(300):
  try:
   with op.open('http://127.0.0.1:8080/health',timeout=2) as x:
    if x.status==200:return
  except Exception:time.sleep(.5)
 raise TimeoutError('Dify health')
def play(player,item,action):
 req=urllib.request.Request('http://127.0.0.1:8080/api/play',data=json.dumps({'player_name':player,'lost_item':item,'action':action}).encode(),headers={'Content-Type':'application/json'})
 with op.open(req,timeout=180) as r:return json.load(r)
wait();player='real-chronology-fixed';turns=[]
items=['\u84dd\u96e8\u4f1e','\u4f1a\u8df3\u821e\u7684\u949f','\u5c0f\u9ec4\u5e3d']
moves=['\u7ed9\u96e8\u4f1e\u9053\u6b49','\u8bf7\u949f\u8df3\u4e00\u652f\u821e','\u544a\u8bc9\u6211\u4e0a\u6b21\u505a\u4e86\u4ec0\u4e48']
for i,(item,move) in enumerate(zip(items,moves)):
 out=play(player,item,move);assert out['memory_saved']=='\u662f'
 assert out['previous_memory_loaded']==('\u5426' if i==0 else '\u662f')
 assert out['workflow_run_id']
 if i:
  expected='\u4e0a\u6b21\u4f60\u5e26\u6765\u201c'+items[i-1]+'\u201d\uff0c\u505a\u4e86\u201c'+moves[i-1]+'\u201d'
  assert expected in out['result'],(expected,out)
 turns.append(out)
isolation=play('different-player-new','\u7ea2\u9774\u5b50','\u8d70\u4e00\u6b65')
assert isolation['previous_memory_loaded']=='\u5426'
report={'status':'PASS','three_actual_workflows':turns,'separate_player':isolation,'network':'none','resource':'2CPU2GiB128PID'}
Path('/data/chronology_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('REAL_DIFY_THREE_TURNS_LATEST_CHOICE_AND_PLAYER_ISOLATION_PASS')
"""
try:
 r=subprocess.run(['docker','exec','-i',name,'/opt/dream-venv/bin/python','-'],env=env,input=inner.encode(),capture_output=True,timeout=480)
 (p/'workflow.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr)[-2000:]
 print(r.stdout.decode(),flush=True)
 info=json.loads(subprocess.check_output(['docker','inspect',name],env=env))[0];assert not info['State']['OOMKilled']
 report=json.loads((data/'chronology_acceptance.json').read_text());report.update({'OOMKilled':False,'actual_memory_limit_bytes':info['HostConfig']['Memory']})
 (p/'chronology_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
finally:subprocess.run(['docker','stop','--time','30',name],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['docker','start',name],env=env,check=True,stdout=subprocess.DEVNULL)
restart=r"""
import urllib.request,json,time
from pathlib import Path
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for _ in range(300):
 try:
  with op.open('http://127.0.0.1:8080/health',timeout=2) as x:
   if x.status==200:break
 except Exception:time.sleep(.5)
else:raise TimeoutError('Restarthealth')
req=urllib.request.Request('http://127.0.0.1:8080/api/play',data=json.dumps({'player_name':'real-chronology-fixed','lost_item':'\u91d1\u94a5\u5319','action':'\u8bf7\u56de\u5fc6\u4e0a\u6b21\u7684\u767b\u8bb0'}).encode(),headers={'Content-Type':'application/json'})
with op.open(req,timeout=180) as x:out=json.load(x)
assert out['previous_memory_loaded']=='\u662f' and out['memory_saved']=='\u662f'
assert '\u4e0a\u6b21\u4f60\u5e26\u6765\u201c\u5c0f\u9ec4\u5e3d\u201d' in out['result']
Path('/data/restart_acceptance.json').write_text(json.dumps({'status':'PASS','turn':out},ensure_ascii=False,indent=2))
print('REAL_DIFY_RESTART_LATEST_MEMORY_PASS')
"""
try:
 r=subprocess.run(['docker','exec','-i',name,'/opt/dream-venv/bin/python','-'],env=env,input=restart.encode(),capture_output=True,timeout=350)
 (p/'restart.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0,(r.stdout+r.stderr)[-1800:]
 shutil.copyfile(data/'restart_acceptance.json',p/'restart_acceptance.json')
 print(r.stdout.decode(),flush=True)
finally:subprocess.run(['docker','stop','--time','30',name],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(p/'result.json').write_text(json.dumps({'status':'PASS','SDK_chronology':'PASS','actual_workflows':5,'fresh_offline2G':'PASS','restart':'PASS','old_failure100_cause':'UNDETERMINED'},indent=2))
print('DIFY_CHRONOLOGY_REPAIR_FULL_ACCEPTANCE_PASS',flush=True)
