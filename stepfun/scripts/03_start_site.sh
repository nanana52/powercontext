#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="$HOME/.config/stepfun/seekdb.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: database credential file missing. Run: bash scripts/01_seekdb_docker.sh" >&2
  exit 1
fi
SEEKDB_PASSWORD="$(sed -n 's/^ROOT_PASSWORD=//p' "$ENV_FILE" | head -n 1)"
if [[ -z "$SEEKDB_PASSWORD" ]]; then
  echo "ERROR: ROOT_PASSWORD is missing in the local credential file." >&2
  exit 1
fi
export SEEKDB_PASSWORD
unset LD_PRELOAD GLIBC_TUNABLES
echo "Starting Fieldnotes on http://localhost:5173 with seekdb Server mode."
exec npm run dev
