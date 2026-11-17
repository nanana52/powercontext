"""Foreground single-container service supervisor; private data stays under /data."""
from pathlib import Path
import json,os,pwd,secrets,signal,subprocess,sys,time,urllib.request
DATA=Path('/data');DATA.mkdir(exist_ok=True);private=DATA/'private';private.mkdir(exist_ok=True);private.chmod(0o700)
ready=DATA/'dream.ready';ready.unlink(missing_ok=True)
p=private/'runtime.json'
if p.exists():cfg=json.loads(p.read_text())
else:
 cfg={k:secrets.token_urlsafe(32) for k in ['postgres','redis','dify_secret','backend']};p.write_text(json.dumps(cfg));p.chmod(0o600)
port=os.environ.get('PORT','8080');processes=[];stopping=False
logs=DATA/'logs';logs.mkdir(exist_ok=True)
def start(name,command,env=None,cwd=None):
 out=(logs/(name+'.log')).open('ab');child=subprocess.Popen(command,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True);out.close();processes.append((name,child));return child

def wait_http(url,timeout=150):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  for name,p in processes:
   if p.poll() is not None:raise RuntimeError(name+' exited; inspect /data/logs/'+name+'.log')
  try:
   with urllib.request.urlopen(url,timeout=2) as r:
    if r.status==200:return
  except Exception:time.sleep(.5)
 raise TimeoutError('Service startup timeout: '+url)

def stop(signum=None,frame=None):
 global stopping
 if stopping:return
 stopping=True;ready.unlink(missing_ok=True)
 for name,p in reversed(processes):
  if p.poll() is None:
   try:os.killpg(p.pid,signal.SIGTERM)
   except ProcessLookupError:pass
 deadline=time.monotonic()+25
 for name,p in reversed(processes):
  try:p.wait(timeout=max(.1,deadline-time.monotonic()))
  except subprocess.TimeoutExpired:
   try:os.killpg(p.pid,signal.SIGKILL)
   except ProcessLookupError:pass
 if signum is not None:raise SystemExit(0)
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
try:
 account=pwd.getpwnam('postgres');pgdata=DATA/'postgres';pgdata.mkdir(exist_ok=True);pgdata.chmod(0o700);os.chown(pgdata,account.pw_uid,account.pw_gid)
 socket=DATA/'postgres_socket';socket.mkdir(exist_ok=True);os.chown(socket,account.pw_uid,account.pw_gid)
 if not (pgdata/'PG_VERSION').exists():
  pw=DATA/'.init-pg-password';pw.write_text(cfg['postgres']);pw.chmod(0o600);os.chown(pw,account.pw_uid,account.pw_gid)
  subprocess.run(['runuser','-u','postgres','--','/usr/lib/postgresql/15/bin/initdb','-D',str(pgdata),'--encoding=UTF8','--locale=C.UTF-8','--auth-local=trust','--auth-host=scram-sha-256','--pwfile='+str(pw)],stdout=sys.stderr,stderr=sys.stderr,check=True);pw.unlink()
 start('postgres',['runuser','-u','postgres','--','/usr/lib/postgresql/15/bin/postgres','-D',str(pgdata),'-h','127.0.0.1','-k',str(socket),'-p','5432','-c','shared_buffers=64MB','-c','max_connections=40'])
 penv=dict(os.environ,PGPASSWORD=cfg['postgres'])
 for _ in range(120):
  if subprocess.run(['/usr/lib/postgresql/15/bin/pg_isready','-h','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
  time.sleep(.5)
 else:raise RuntimeError('PostgreSQL startup failed')
 exists=subprocess.check_output(['/usr/lib/postgresql/15/bin/psql','-h','127.0.0.1','-U','postgres','-d','postgres','-tAc',"SELECT 1 FROM pg_database WHERE datname='dify'"],env=penv,text=True).strip()
 if not exists:subprocess.run(['/usr/lib/postgresql/15/bin/createdb','-h','127.0.0.1','-U','postgres','dify'],env=penv,check=True)
 redisdir=DATA/'redis';redisdir.mkdir(exist_ok=True);redisconf=private/'redis.conf';redisconf.write_text('bind 127.0.0.1\nport 6379\ndir '+str(redisdir)+'\nrequirepass '+cfg['redis']+'\nappendonly yes\n');redisconf.chmod(0o600)
 start('redis',['redis-server',str(redisconf)])
 start('model',['/opt/dream-model/llama-b12248/llama-server','-m','/opt/dream-model/qwen2.5-0.5b-instruct-q4_k_m.gguf','--host','127.0.0.1','--port','18081','-c','4096','-t','2','--alias','qwen-local'])
 common=dict(os.environ,PORT=port,DREAM_ACCESS_TOKEN=cfg['backend'],DREAM_DATA_DIR=str(DATA/'memory'),DREAM_MODEL_URL='http://127.0.0.1:18081/v1',DREAM_ALLINONE='1',DREAM_READY_FILE=str(ready),DREAM_DIFY_PRIVATE=str(private/'dify_app.json'),PYTHONDONTWRITEBYTECODE='1')
 # Separate venv keeps the official PowerContext SDK dependencies isolated from Dify.
 start('backend',['/opt/dream-venv/bin/python','-m','uvicorn','app:app','--host','0.0.0.0','--port',port],env=common,cwd='/opt/dream/backend')
 denv=dict(common,PATH='/app/api/.venv/bin:'+os.environ['PATH'],FLASK_APP='app',MODE='api',MIGRATION_ENABLED='false',SECRET_KEY=cfg['dify_secret'],DB_TYPE='postgresql',DB_HOST='127.0.0.1',DB_PORT='5432',DB_USERNAME='postgres',DB_PASSWORD=cfg['postgres'],DB_DATABASE='dify',REDIS_HOST='127.0.0.1',REDIS_PORT='6379',REDIS_PASSWORD=cfg['redis'],CELERY_BROKER_URL='redis://:'+cfg['redis']+'@127.0.0.1:6379/1',STORAGE_TYPE='local',STORAGE_LOCAL_PATH=str(DATA/'dify_storage'),DIFY_BIND_ADDRESS='127.0.0.1',DIFY_PORT='5001',SERVER_WORKER_AMOUNT='1',SERVER_WORKER_CONNECTIONS='20',SERVER_WORKER_CLASS='gevent',CELERY_WORKER_AMOUNT='1',CELERY_WORKER_CLASS='gevent',CELERY_QUEUES='workflow,workflow_storage,conversation,api_token',LOG_LEVEL='WARNING',SSRF_PROXY_ALL_URL='',SSRF_PROXY_HTTP_URL='',SSRF_PROXY_HTTPS_URL='',CONSOLE_API_URL='http://127.0.0.1:5001',SERVICE_API_URL='http://127.0.0.1:5001',APP_WEB_URL='http://127.0.0.1:'+port,VECTOR_STORE='qdrant',QDRANT_URL='http://127.0.0.1:6333',PLUGIN_DAEMON_URL='http://127.0.0.1:5002')
 with (logs/'migration.log').open('ab') as out:subprocess.run(['/app/api/.venv/bin/flask','upgrade-db'],env=denv,cwd='/app/api',stdout=out,stderr=out,check=True,timeout=180)
 start('dify-api',['/bin/bash','/entrypoint.sh'],env=denv,cwd='/app/api')
 start('dify-worker',['/bin/bash','/entrypoint.sh'],env=dict(denv,MODE='worker'),cwd='/app/api')
 wait_http('http://127.0.0.1:18081/health');wait_http('http://127.0.0.1:'+port+'/internal/core-health');wait_http('http://127.0.0.1:5001/health')
 with (logs/'publish.log').open('ab') as out:subprocess.run(['/app/api/.venv/bin/python','/opt/dream/backend/bootstrap_dify.py'],env=denv,cwd='/app/api',stdout=out,stderr=out,check=True,timeout=90)
 ready.write_text('ready');print('DIFY_POWERCONTEXT_REAL_MODEL_GAME_READY port='+port,flush=True)
 while True:
  time.sleep(1)
  for name,p in processes:
   if p.poll() is not None:raise RuntimeError(name+' exited; inspect /data/logs/'+name+'.log')
finally:stop()
