#!/usr/bin/env bash
# 打包工程为干净 tarball（排除密钥/虚拟环境/运行时产物），便于 scp 上传到服务器
# 用法：bash deploy/package.sh   -> 生成 superagent-<ts>.tar.gz
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/superagent-deploy.tar.gz"

tar -czf "$OUT" \
  -C "$ROOT" \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='.venv' \
  --exclude='.venv/*' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.idea' \
  --exclude='.git' \
  --exclude='data' \
  --exclude='projects' \
  --exclude='01_需求文档' \
  --exclude='*.db' \
  --exclude='*.zip' \
  --exclude='tests' \
  --exclude='superagent-deploy.tar.gz' \
  .

echo "已生成：$OUT ($(du -h "$OUT" | cut -f1))"
