#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${DREAM_RUNTIME_DIR:-$ROOT/.runtime}"
for component in backend model; do
  file="$RUNTIME/$component.pid"
  [ -f "$file" ] || continue
  pid="$(cat "$file")"
  if [ -r "/proc/$pid/cmdline" ]; then
    command="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
    case "$command" in
      *"$RUNTIME"*) kill "$pid" ;;
      *) echo "PID $pid no longer belongs to this deployment; left untouched." ;;
    esac
  fi
done
