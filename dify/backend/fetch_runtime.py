"""Checksum-locked build downloads with bounded reads, retries and resume."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,os,re,shutil,tarfile,time,urllib.request
CACHE=Path('/tmp/dream-model-cache');DEST=Path('/opt/dream-model');DEST.mkdir(parents=True,exist_ok=True)
ASSETS=[
 ('qwen2.5-0.5b-instruct-q4_k_m.gguf','https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/master/qwen2.5-0.5b-instruct-q4_k_m.gguf','74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db',491400032),
 ('llama.tar.gz','https://github.com/ggml-org/llama.cpp/releases/download/b12248/llama-b12248-bin-ubuntu-x64.tar.gz','6b3a530b44f6b0a4ae4872d3b3c8d1edc2ac6bba7d8bd211329a4ba644c0dc65',23157778),
]
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def fetch(asset):
 name,url,sha,size=asset;target=DEST/name;cached=CACHE/name
 if cached.is_file() and cached.stat().st_size==size and digest(cached)==sha:
  shutil.copyfile(cached,target);print('VERIFIED_CACHE '+name,flush=True);return target
 if target.is_file() and target.stat().st_size==size and digest(target)==sha:return target
 partial=target.with_suffix(target.suffix+'.part');deadline=time.monotonic()+600
 for attempt in range(5):
  offset=partial.stat().st_size if partial.exists() else 0
  if offset>size:partial.unlink();offset=0
  try:
   if time.monotonic()>=deadline:raise TimeoutError('Download deadline exceeded: '+name)
   headers={'User-Agent':'DreamGame-reproducible-build/1.0'}
   if offset:headers['Range']='bytes='+str(offset)+'-'
   req=urllib.request.Request(url,headers=headers)
   with urllib.request.urlopen(req,timeout=30) as response:
    if offset:
     content_range=response.headers.get('Content-Range','')
     if response.status==206:
      if not content_range.startswith('bytes '+str(offset)+'-'):raise RuntimeError('Unexpected resume range')
     else:offset=0
    mode='ab' if offset else 'wb';received=offset;last=offset
    with partial.open(mode) as f:
     while True:
      if time.monotonic()>=deadline:raise TimeoutError('Download deadline exceeded: '+name)
      chunk=response.read(65536)
      if not chunk:break
      f.write(chunk);received+=len(chunk)
      if received>size:raise RuntimeError('Asset exceeds expected size')
      if received-last>=8*1024*1024:print('DOWNLOAD '+name+' '+str(received)+'/'+str(size),flush=True);last=received
   if partial.stat().st_size!=size:raise RuntimeError('Incomplete download: '+name)
   if digest(partial)!=sha:
    partial.unlink();raise RuntimeError('Asset checksum mismatch: '+name)
   partial.replace(target);print('VERIFIED_DOWNLOAD '+name,flush=True);return target
  except Exception as error:
   print('DOWNLOAD_RETRY '+name+' attempt='+str(attempt+1)+' reason='+type(error).__name__,flush=True)
   if attempt==4 or time.monotonic()>=deadline:raise
   time.sleep(min(2*(attempt+1),8))
 raise RuntimeError('Unable to download '+name)
def main():
 with ThreadPoolExecutor(max_workers=2) as executor:paths=list(executor.map(fetch,ASSETS))
 for target in paths:
  if target.name.endswith('.gz'):
   with tarfile.open(target) as archive:archive.extractall(DEST,filter='data')
   target.unlink()
 print('MODEL_AND_RUNTIME_CHECKSUMS_PASS',flush=True)
if __name__=='__main__':main()
