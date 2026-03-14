#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Compose: containers =="
docker compose ps

echo
echo "== Compose: images =="
docker compose images

echo
echo "== Compose: network(s) =="
docker network ls | grep maturity-tool || true

echo
echo "== Compose: volume(s) =="
docker volume ls | grep maturity-tool || true

if docker volume inspect maturity-tool_postgres_data >/dev/null 2>&1; then
  echo
  echo "== Postgres volume mountpoint =="
  docker volume inspect maturity-tool_postgres_data --format '{{.Mountpoint}}'
fi

echo
echo "== Live resource usage (docker stats) =="
docker stats --no-stream

echo
echo "== Docker disk usage summary =="
docker system df
