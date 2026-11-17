#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
image="${DREAM_IMAGE:-dream-dify-complete:local}"
docker build -t "$image" .
docker volume create dream-dify-data >/dev/null
exec docker run --rm --name dream-dify-game --cpus=2 --memory=3g --pids-limit=256 -p "127.0.0.1:${DREAM_HTTP_PORT:-8080}:8080" -v dream-dify-data:/data "$image"
