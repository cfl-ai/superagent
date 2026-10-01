FROM python:3.12-slim

WORKDIR /app

# 仅复制运行所需（零第三方依赖）
COPY superagent ./superagent
COPY config ./config
COPY pyproject.toml README.md LICENSE ./

# 安装 ffmpeg（视频剪辑管线）。如需中文字幕，可追加 fonts-noto-cjk
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ".[file]" && rm -rf /root/.cache

EXPOSE 8000

# 密钥通过运行时环境变量注入（docker-compose env_file / -e）
ENV PYTHONUNBUFFERED=1

# 健康检查：容器内自测 /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["python", "-m", "superagent", "serve", "--host", "0.0.0.0", "--port", "8000"]
