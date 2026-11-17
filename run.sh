#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/dify"
exec bash run.sh "$@"
