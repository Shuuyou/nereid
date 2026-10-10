#!/bin/bash
# 启动 SecAgent API（幂等：先杀旧进程再起新实例）
cd "$(dirname "$0")/../backend"
pgrep -f "uvicorn app.main:app" | xargs -r kill 2>/dev/null
sleep 2
source .venv/bin/activate
export PYTHONPATH=.
exec setsid uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/api.log 2>&1 < /dev/null
