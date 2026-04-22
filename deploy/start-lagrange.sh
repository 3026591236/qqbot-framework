#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

if command -v docker-compose >/dev/null 2>&1; then
  docker-compose -f deploy/docker-compose.lagrange.yml up -d --build
else
  docker compose -f deploy/docker-compose.lagrange.yml up -d --build
fi

echo "Started qqbot-framework + Lagrange.OneBot"
echo "View logs with: docker logs -f lagrange-onebot"
