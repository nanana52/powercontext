"""Fetch exact official dependencies into private runtime; verify every byte."""
from pathlib import Path
import argparse,hashlib,json,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
WHEEL_URL='https://files.pythonhosted.org/packages/d2/e5/8d23a9108d1e84e8b7cae2bab67dc0095a519c958c2e4012bc96a6dc1aad/powercontext-1.2.0-py3-none-any.whl'
WHEEL_SHA='9bb55ec13bb2fc1ac84038d917042cc2890ffab4aeedacf1cd5ba5329dcb84b9'
DIFY_COMMIT='50abea97062110044f15d0e03ccecadd9ccc87ca'
def download(url,path,expected):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:return path
 for attempt in range(3):
  try:
   with urllib.request.urlopen(url,timeout=60) as response:content=response.read()
   if hashlib.sha256(content).hexdigest()!=expected:raise RuntimeError('Dependency SHA256 mismatch: '+path.name)
   temporary=path.with_suffix(path.suffix+'.part');temporary.write_bytes(content);temporary.replace(path);return path
  except Exception:
   if attempt==2:raise
   time.sleep(1)
def wheel(path=None):
 return download(WHEEL_URL,path or ROOT/'.runtime/vendor/powercontext-1.2.0-py3-none-any.whl',WHEEL_SHA)
def dify():
 source=ROOT/'deployment/upstream_docker'
 manifest=json.loads((ROOT/'deployment/upstream_manifest.json').read_text())
 for name,expected in manifest.items():
  path=source/name
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
   raise RuntimeError('Delivered upstream configuration mismatch: '+name)
 return source
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--wheel');p.add_argument('--dify',action='store_true');a=p.parse_args()
 print(dify() if a.dify else wheel(a.wheel))
