#!/usr/bin/env bash
# SuperAgent 桌面版一键启动（Linux/macOS）
cd "$(dirname "$0")"
python3 -m superagent serve --host 127.0.0.1 --port 8000 &
sleep 2
( xdg-open http://localhost:8000 2>/dev/null || open http://localhost:8000 2>/dev/null ) &
echo "SuperAgent 已启动：http://localhost:8000"
wait
