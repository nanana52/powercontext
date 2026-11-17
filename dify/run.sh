#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec "${DREAM_PYTHON:-python3}" scripts/verify_full_stack.py "$@"
