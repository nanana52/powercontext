#!/usr/bin/env bash
set -euo pipefail

NAME=stepfun-seekdb
CONFIG_DIR="$HOME/.config/stepfun"
ENV_FILE="$CONFIG_DIR/seekdb.env"

command -v docker >/dev/null || { echo "ERROR: Docker is required." >&2; exit 1; }
command -v openssl >/dev/null || { echo "ERROR: OpenSSL is required." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "ERROR: Docker daemon is not running." >&2; exit 1; }

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

exists=false
if docker ps -a --format '{{.Names}}' | grep -Fxq "$NAME"; then
  exists=true
fi
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ "$exists" == true ]]; then
    echo "ERROR: Existing container found, but local password file is missing: $ENV_FILE" >&2
    echo "Preserve the container; recover its original credentials before continuing." >&2
    exit 1
  fi
  ( umask 077; printf 'ROOT_PASSWORD=%s\n' "$(openssl rand -hex 16)" > "$ENV_FILE" )
fi
chmod 600 "$ENV_FILE"

if [[ "$exists" == true ]]; then
  echo "Reusing existing container $NAME"
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME")" != "true" ]]; then
    docker start "$NAME" >/dev/null
  fi
else
  docker volume create stepfun-seekdb-data >/dev/null
  docker run -d --name "$NAME" --restart unless-stopped \
    -p 127.0.0.1:2881:2881 \
    --env-file "$ENV_FILE" \
    -e SEEKDB_DATABASE=test \
    -e MEMORY_LIMIT=2G \
    -e LOG_DISK_SIZE=2G \
    -e DATAFILE_SIZE=2G \
    -v stepfun-seekdb-data:/var/lib/seekdb \
    oceanbase/seekdb:latest >/dev/null
fi

echo "Checking real seekdb SQL readiness..."
for i in $(seq 1 60); do
  if docker exec "$NAME" sh -lc \
    'MYSQL_PWD="$ROOT_PASSWORD" mysql -h127.0.0.1 -P2881 -uroot -Dtest -N -e "SELECT 1;"' \
    2>/dev/null | grep -qx '1'; then
    echo "PASS: seekdb Server is ready (SELECT 1)."
    exit 0
  fi
  sleep 2
done
echo "ERROR: seekdb SQL readiness check failed. Inspect: docker logs --tail 80 $NAME" >&2
exit 1
