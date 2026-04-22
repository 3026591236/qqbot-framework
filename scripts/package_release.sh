#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
rm -f qqbot-framework-release.tar.gz
rm -rf build-release
mkdir -p build-release
cp -r app deploy docs scripts user_plugins .env.example .gitignore Dockerfile docker-compose.yml install_plugin.py market.example.json requirements.txt run.sh README.md DEPLOY_FINAL.md VERSION build-release/

rm -rf build-release/.venv \
       build-release/__pycache__ \
       build-release/app/__pycache__ \
       build-release/app/*/__pycache__ \
       build-release/user_plugins/__pycache__ \
       build-release/docs/__pycache__ \
       build-release/logs \
       build-release/data \
       build-release/ntqq \
       build-release/napcat \
       build-release/build-release

mkdir -p build-release/napcat/config

tar -czf qqbot-framework-release.tar.gz -C build-release .
echo "Created: $(pwd)/qqbot-framework-release.tar.gz"
