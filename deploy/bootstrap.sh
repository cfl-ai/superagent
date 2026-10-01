#!/usr/bin/env bash
# SuperAgent 一键部署（Docker）。在服务器上执行：sudo bash deploy/bootstrap.sh
# 自动：检测/安装 Docker → 写 .env → 构建启动 → 健康检查。不影响现有项目。
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/superagent}"
PORT="${PORT:-8000}"
cd "$APP_DIR"

echo "==> 检测 Docker"
if ! command -v docker >/dev/null 2>&1; then
    echo "未安装 Docker，尝试自动安装..."
    if command -v apt-get >/dev/null 2>&1; then
        curl -fsSL https://get.docker.com | sh
    elif command -v yum >/dev/null 2>&1; then
        curl -fsSL https://get.docker.com | sh
    else
        echo "无法识别系统包管理器，请手动安装 Docker：https://docs.docker.com/engine/install/"
        exit 1
    fi
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "缺少 docker compose 插件，请安装 docker-compose-plugin"; exit 1
fi

echo "==> 准备 .env"
if [ ! -f .env ]; then
    if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
        cat > .env <<EOF
SUPERAGENT_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY
EOF
    else
        cp .env.example .env
        echo "已生成 .env 模板，请编辑填入 DEEPSEEK_API_KEY 后重新运行本脚本"; exit 1
    fi
fi

echo "==> 构建并启动（端口 $PORT，独立容器，限制 1 CPU / 1G 内存）"
PORT=$PORT docker compose up -d --build

echo "==> 健康检查"
sleep 3
if curl -fsS "http://127.0.0.1:$PORT/health"; then
    echo
    echo "✅ SuperAgent 部署成功：http://127.0.0.1:$PORT"
else
    echo "❌ 健康检查失败，查看日志：docker compose logs superagent"
    exit 1
fi
