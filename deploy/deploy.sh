#!/usr/bin/env bash
# SuperAgent 部署脚本（systemd + venv，无 Docker 依赖）
# 在服务器上以 root 执行：sudo bash deploy/deploy.sh
# 不影响现有项目：独立目录 /opt/superagent + 独立端口 8000 + 独立 systemd 服务
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/superagent}"
PORT="${PORT:-8000}"
PY="python3"

echo "==> 安装系统依赖（若缺失）"
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "未找到 $PY，请先安装 Python 3.10+"; exit 1
fi

echo "==> 创建目录与用户"
mkdir -p "$APP_DIR"
id -u superagent >/dev/null 2>&1 || useradd --system --no-create-home --home-dir "$APP_DIR" superagent

echo "==> 创建虚拟环境"
if [ ! -d "$APP_DIR/venv" ]; then
    "$PY" -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/venv/bin/pip" install "$APP_DIR" >/dev/null

echo "==> 准备 .env（若不存在）"
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" <<'ENV'
SUPERAGENT_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=请替换为你的密钥
ENV
    echo "已生成 $APP_DIR/.env 模板，请填入密钥后重启服务"
fi

echo "==> 安装 systemd 服务"
sed "s|/opt/superagent|$APP_DIR|g; s|--port 8000|--port $PORT|g" \
    "$APP_DIR/deploy/systemd/superagent.service" > /etc/systemd/system/superagent.service
systemctl daemon-reload
systemctl enable superagent
systemctl restart superagent

echo "==> 等待启动并健康检查"
sleep 2
curl -fsS "http://127.0.0.1:$PORT/health" && echo || { echo "健康检查失败"; systemctl status superagent --no-pager; exit 1; }
echo
echo "✅ SuperAgent 已部署：http://127.0.0.1:$PORT"
echo "   查看状态：systemctl status superagent"
echo "   查看日志：journalctl -u superagent -f"
