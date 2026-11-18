#!/usr/bin/env bash
# AAM · AI 账号聚合面板 — 启动脚本
# 用法：bash start.sh [端口]   （默认 8710，监听 0.0.0.0）
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8710}"

# 加载 .env（存在时）
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ ! -x venv/bin/python ]; then
  echo "未找到 venv，请先运行：bash install.sh" >&2
  exit 1
fi

echo "==> AAM 聚合面板启动于 http://0.0.0.0:${PORT}"
echo "    面板密钥：首次访问时生成，见 data/admin_key.txt"
exec venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"