#!/usr/bin/env bash
# 捞针·Nereid 前端生产启动（standalone 模式需手动补齐静态资源）
set -e
cd "$(dirname "$0")/../frontend"
PORT="${PORT:-3200}"
export PORT HOSTNAME=0.0.0.0 BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

if [ ! -f .next/standalone/server.js ]; then
  echo "[start] standalone 产物不存在，先 npm run build"
  npm run build
fi
# standalone 不自动包含静态资源与 public（Next.js 官方要求手动拷贝）
cp -r .next/static .next/standalone/.next/static 2>/dev/null || true
mkdir -p .next/standalone/public && cp -r public/* .next/standalone/public/ 2>/dev/null || true

echo "[start] frontend on :$PORT (BACKEND_URL=$BACKEND_URL)"
exec node .next/standalone/server.js
