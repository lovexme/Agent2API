#!/usr/bin/env bash
# AAM 聚合面板 · 一键安装脚本
# 用法：bash install.sh
# 作用：创建 venv、安装后端依赖、初始化数据目录、生成 .env（随机签名密钥）
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 检查 Python"
PY=${PYTHON:-python3}
$PY -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10+"'
echo "    $( $PY --version )"

echo "==> 创建虚拟环境 venv/"
$PY -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

echo "==> 安装依赖"
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> 初始化数据目录 data/"
mkdir -p data

echo "==> 生成 .env（如已存在则跳过）"
if [ ! -f .env ]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    SIGN=$(openssl rand -hex 32)
  else
    SIGN=$($PY -c 'import secrets; print(secrets.token_hex(32))')
  fi
  # 替换占位符为随机值
  $PY - "$SIGN" <<'PYEOF'
import sys, pathlib
p = pathlib.Path('.env')
s = p.read_text(encoding='utf-8')
s = s.replace('CHANGE_ME_32_hex_sign_secret_000000000000', sys.argv[1])
p.write_text(s, encoding='utf-8')
PYEOF
  echo "    已生成 .env（AAM_SIGN_KEY 已随机化）"
else
  echo "    .env 已存在，未覆盖"
fi

chmod +x start.sh
echo ""
echo "==> 安装完成。启动：bash start.sh"
echo "    首次启动会自动创建 SQLite 数据库与面板密钥（data/admin_key.txt）"
