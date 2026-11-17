#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
RUNTIME="${DREAM_RUNTIME_DIR:-$ROOT/.runtime}"
mkdir -p "$RUNTIME/models" "$RUNTIME/logs" "$RUNTIME/data"
PYTHON="${DREAM_PYTHON:-}"
if [ -z "$PYTHON" ] && command -v python3.12 >/dev/null 2>&1; then
  PYTHON="$(command -v python3.12)"
fi
if [ -z "$PYTHON" ] && python3 -c 'import sys;raise SystemExit(sys.version_info[:2] != (3,12))' 2>/dev/null; then
  PYTHON="$(command -v python3)"
fi
if [ -z "$PYTHON" ]; then
  if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
  else
    # Bootstrap tooling inside this deployment, including on PEP 668 systems.
    python3 -m venv "$RUNTIME/bootstrap"
    "$RUNTIME/bootstrap/bin/python" -m pip install 'uv==0.9.9'
    UV="$RUNTIME/bootstrap/bin/uv"
  fi
  "$UV" python install 3.12.12
  PYTHON="$("$UV" python find 3.12.12)"
fi
"$PYTHON" -c 'import sys;raise SystemExit(sys.version_info[:2] != (3,12))'
MODEL_PORT="${DREAM_MODEL_PORT:-18081}"
BACKEND_PORT="${DREAM_BACKEND_PORT:-18090}"
if [ ! -x "$RUNTIME/venv/bin/python" ]; then
  "$PYTHON" -m venv "$RUNTIME/venv"
fi
"$RUNTIME/venv/bin/python" -m pip install --disable-pip-version-check -r backend/requirements.txt
"$RUNTIME/venv/bin/python" "$ROOT/scripts/fetch_dependencies.py" --wheel "$RUNTIME/powercontext-1.2.0-py3-none-any.whl"
"$RUNTIME/venv/bin/python" -m pip install --no-deps "$RUNTIME/powercontext-1.2.0-py3-none-any.whl"
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
if ! curl -fsS http://127.0.0.1:$MODEL_PORT/health >/dev/null 2>&1; then
  nohup "$LLAMA/llama-b12248/llama-server" -m "$MODEL" --host 127.0.0.1 --port "$MODEL_PORT" -c 4096 -t 4 --alias qwen-local >"$RUNTIME/logs/model.log" 2>&1 </dev/null &
  echo "$!" > "$RUNTIME/model.pid"
fi
unset PYTHONPATH
export DREAM_ACCESS_TOKEN="$(cat "$RUNTIME/access.token")"
export DREAM_DATA_DIR="$RUNTIME/data"
export DREAM_MODEL_URL=http://127.0.0.1:$MODEL_PORT/v1
if ! curl -fsS http://127.0.0.1:$BACKEND_PORT/health >/dev/null 2>&1; then
  cd "$ROOT/backend"
  nohup "$RUNTIME/venv/bin/python" -m uvicorn app:app --host "${DREAM_LISTEN_HOST:-0.0.0.0}" --port "$BACKEND_PORT" >"$RUNTIME/logs/backend.log" 2>&1 </dev/null &
  echo "$!" > "$RUNTIME/backend.pid"
fi
echo "Backend URL for Dify Docker on Linux: http://172.17.0.1:$BACKEND_PORT"
echo "Private access token file: $RUNTIME/access.token"
echo "Model health: http://127.0.0.1:$MODEL_PORT/health"
echo "Backend health: http://127.0.0.1:$BACKEND_PORT/health"

for component in model backend; do
  if [ "$component" = model ]; then port="$MODEL_PORT"; else port="$BACKEND_PORT"; fi
  ready=0
  for attempt in $(seq 1 90); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ready=1; break; fi
    if [ -f "$RUNTIME/$component.pid" ] && ! kill -0 "$(cat "$RUNTIME/$component.pid")" 2>/dev/null; then break; fi
    sleep 1
  done
  if [ "$ready" != 1 ]; then echo "$component failed; see $RUNTIME/logs/$component.log" >&2; exit 1; fi
done
echo "MODEL_AND_POWERCONTEXT_HEALTH_PASS"
