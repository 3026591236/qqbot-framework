#!/bin/sh
set -eu

BASE_DIR=${1:-$(pwd)}
APP_DIR="$BASE_DIR/qqbot-framework"
LAGRANGE_DIR="$APP_DIR/lagrange"

mkdir -p "$APP_DIR/data"
mkdir -p "$LAGRANGE_DIR/data"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/deploy/.env.lagrange.example" "$APP_DIR/.env"
  echo "Created $APP_DIR/.env"
fi

if [ ! -f "$LAGRANGE_DIR/data/appsettings.json" ]; then
  cp "$APP_DIR/deploy/lagrange.appsettings.example.json" "$LAGRANGE_DIR/data/appsettings.json"
  echo "Created $LAGRANGE_DIR/data/appsettings.json"
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit $APP_DIR/.env and fill QQBOT_OWNER_IDS"
echo "2. Review $LAGRANGE_DIR/data/appsettings.json"
echo "3. Run: cd $APP_DIR && docker compose -f deploy/docker-compose.lagrange.yml up -d --build"
