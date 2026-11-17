"""Foreground supervisor for the real local model and PowerContext adapter."""
from pathlib import Path
import os,secrets,signal,subprocess,sys,time,urllib.request
DATA=Path(os.environ.get('DREAM_DATA_DIR','/data'));DATA.mkdir(parents=True,exist_ok=True)
if not os.environ.get('DREAM_ACCESS_TOKEN'):
 p=DATA/'access.token'
 if not p.exists():p.write_text(secrets.token_urlsafe(32));p.chmod(0o600)
 os.environ['DREAM_ACCESS_TOKEN']=p.read_text().strip()
model=None
if not os.environ.get('DREAM_MODEL_URL'):
 model=subprocess.Popen(['/opt/dream-model/llama-b12248/llama-server','-m','/opt/dream-model/qwen2.5-0.5b-instruct-q4_k_m.gguf','--host','127.0.0.1','--port','18081','-c','4096','-t','2','--alias','qwen-local'],stdin=subprocess.DEVNULL,stdout=sys.stderr,stderr=sys.stderr)
 os.environ['DREAM_MODEL_URL']='http://127.0.0.1:18081/v1'
 try:
  for _ in range(90):
   if model.poll() is not None:raise RuntimeError('Local model exited')
   try:
    with urllib.request.urlopen('http://127.0.0.1:18081/health',timeout=1):break
   except Exception:time.sleep(1)
  else:raise RuntimeError('Local model startup timeout')
 except BaseException:
  model.terminate();model.wait(timeout=15);raise
try:
 import uvicorn
 uvicorn.run('app:app',host='0.0.0.0',port=18090)
finally:
 if model is not None:
  model.terminate()
  try:model.wait(timeout=15)
  except subprocess.TimeoutExpired:model.kill();model.wait()
