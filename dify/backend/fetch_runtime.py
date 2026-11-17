"""Build-time downloads are checksum-locked; cache files are optional."""
from pathlib import Path
import hashlib,shutil,tarfile,urllib.request
CACHE=Path('/tmp/dream-model-cache');DEST=Path('/opt/dream-model');DEST.mkdir(parents=True,exist_ok=True)
assets=[
 ('qwen2.5-0.5b-instruct-q4_k_m.gguf','https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/master/qwen2.5-0.5b-instruct-q4_k_m.gguf','74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db'),
 ('llama.tar.gz','https://github.com/ggml-org/llama.cpp/releases/download/b12248/llama-b12248-bin-ubuntu-x64.tar.gz','6b3a530b44f6b0a4ae4872d3b3c8d1edc2ac6bba7d8bd211329a4ba644c0dc65'),
]
for name,url,sha in assets:
 source=CACHE/name
 if not source.is_file():
  source=DEST/name
  urllib.request.urlretrieve(url,source)
 assert hashlib.sha256(source.read_bytes()).hexdigest()==sha,name
 target=DEST/name
 if source!=target:shutil.copyfile(source,target)
 if name.endswith('.gz'):
  with tarfile.open(target) as archive:archive.extractall(DEST,filter='data')
  target.unlink()
print('MODEL_AND_RUNTIME_CHECKSUMS_PASS')
