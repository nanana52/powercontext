#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
if [[ -z "${MINIMAX_API_KEY:-}" ]]; then
  echo "请先设置 MiniMax API Key，当前不允许伪造模型调用结果。"
  echo "Linux 终端输入：read -rs -p 'MiniMax Key: ' MINIMAX_API_KEY; echo; export MINIMAX_API_KEY"
  exit 2
fi
if ! python3 -c "import sys; assert sys.version_info >= (3,11)" 2>/dev/null; then
  echo "Python 3.11+ required. Use GitHub Codespaces Ubuntu." >&2
  exit 2
fi
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install "powercontext[cli,server]==1.4.1" pylibseekdb pymysql
export PATH="$PWD/.venv/bin:$PATH"
export PYTHONPATH="$PWD"
python -m sdd.run
