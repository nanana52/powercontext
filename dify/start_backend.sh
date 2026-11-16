#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
RUNTIME="${DREAM_RUNTIME_DIR:-$ROOT/.runtime}"
mkdir -p "$RUNTIME/models" "$RUNTIME/logs" "$RUNTIME/data"
if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --user 'uv==0.9.9'
  export PATH="$HOME/.local/bin:$PATH"
fi
uv python install 3.12.12
if [ ! -x "$RUNTIME/venv/bin/python" ]; then
  uv venv --python 3.12.12 "$RUNTIME/venv"
fi
uv pip install --python "$RUNTIME/venv/bin/python" -r backend/requirements.txt
if [ ! -f "$RUNTIME/access.token" ]; then
  "$RUNTIME/venv/bin/python" -c 'import secrets,sys,pathlib; p=pathlib.Path(sys.argv[1]);p.write_text(secrets.token_urlsafe(32));p.chmod(0o600)' "$RUNTIME/access.token"
fi
MODEL="$RUNTIME/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
LLAMA="$RUNTIME/llama"
if [ ! -f "$MODEL" ]; then
  curl -fL --retry 3 --retry-delay 2 'https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/master/qwen2.5-0.5b-instruct-q4_k_m.gguf' -o "$MODEL"
fi
echo "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db  $MODEL" | sha256sum -c -
if [ ! -x "$LLAMA/llama-b12248/llama-server" ]; then
  curl -fL --retry 3 --retry-delay 2 'https://github.com/ggml-org/llama.cpp/releases/download/b12248/llama-b12248-bin-ubuntu-x64.tar.gz' -o "$RUNTIME/llama.tar.gz"
  echo "6b3a530b44f6b0a4ae4872d3b3c8d1edc2ac6bba7d8bd211329a4ba644c0dc65  $RUNTIME/llama.tar.gz" | sha256sum -c -
  mkdir -p "$LLAMA"
  tar -xzf "$RUNTIME/llama.tar.gz" -C "$LLAMA"
fi
if ! curl -fsS http://127.0.0.1:18081/health >/dev/null 2>&1; then
  nohup "$LLAMA/llama-b12248/llama-server" -m "$MODEL" --host 127.0.0.1 --port 18081 -c 4096 -t 4 --alias qwen-local >"$RUNTIME/logs/model.log" 2>&1 </dev/null &
  echo "$!" > "$RUNTIME/model.pid"
fi
export PYTHONPATH="$ROOT/vendor/powercontext/src"
export DREAM_ACCESS_TOKEN="$(cat "$RUNTIME/access.token")"
export DREAM_DATA_DIR="$RUNTIME/data"
export DREAM_MODEL_URL=http://127.0.0.1:18081/v1
if ! curl -fsS http://127.0.0.1:18090/health >/dev/null 2>&1; then
  cd "$ROOT/backend"
  nohup "$RUNTIME/venv/bin/python" -m uvicorn app:app --host "${DREAM_LISTEN_HOST:-0.0.0.0}" --port 18090 >"$RUNTIME/logs/backend.log" 2>&1 </dev/null &
  echo "$!" > "$RUNTIME/backend.pid"
fi
echo "Backend URL for Dify Docker on Linux: http://172.17.0.1:18090"
echo "Private access token file: $RUNTIME/access.token"
echo "Model health: http://127.0.0.1:18081/health"
echo "Backend health: http://127.0.0.1:18090/health"
