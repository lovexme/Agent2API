#!/usr/bin/env bash
# AAM · 可选外部网关一键部署
# 部署 WorkBuddy(wb2api 7863) 与 Trae(trae2api 8770) 两个可选网关。
# 它们仍是独立服务（由各自上游维护），这里只负责「获取 + 配置 + systemd 托管」，
# 不把上游源码打进本仓库。不装也不影响 AAM 面板本身与 Tabbit/Loomy。
#
# 用法：
#   bash deploy-gateways.sh                # 部署全部可选网关（workbuddy + trae）
#   bash deploy-gateways.sh workbuddy      # 只部署 WorkBuddy 网关
#   bash deploy-gateways.sh trae           # 只部署 Trae 网关
#   AAM_TOOLS_DIR=/opt/aam gateways ...    # 安装到指定目录（默认本目录 ./gateways）
#
# 选项：
#   AAM_WB2API_VERSION=latest   # wb2api 版本 tag（默认 latest）
#   AAM_SKIP_SYSTEMD=1          # 不装 systemd（前台运行,调试用）
#   AAM_WB2API_PORT=7863        # WorkBuddy 网关端口（默认 7863）
#   AAM_TRAE_PORT=8770          # Trae 网关端口（默认 8770）

set -euo pipefail
cd "$(dirname "$0")"

TOOLS_DIR="${AAM_TOOLS_DIR:-$PWD/gateways}"
WB_PORT="${AAM_WB2API_PORT:-7863}"
TRAE_PORT="${AAM_TRAE_PORT:-8770}"
mkdir -p "$TOOLS_DIR"
LOG="> ${TOOLS_DIR}/deploy.log 2>&1"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "  ✗ 缺少依赖: $1（$2）"; exit 1
  fi
}
detail() { echo "==> $*"; }
ok() { echo "    ✓ $*"; }
fail() { echo "    ✗ $*"; exit 1; }

############################## WorkBuddy (wb2api 7863) ##############################
install_workbuddy() {
  detail "WorkBuddy 网关 (wb2api)"
  need curl "apt install -y curl"
  local REPO="linguo2625469/workbuddy2api-panel"
  local TAG="${AAM_WB2API_VERSION:-latest}"
  local VER
  VER=$(curl -fsSL --retry 3 "https://api.github.com/repos/${REPO}/releases/${TAG}" | python3 -c "import sys,json;print(json.load(sys.stdin)['tag_name'])" 2>/dev/null) \
    || fail "获取 wb2api 版本失败(网络? 需可访问 github.com)"
  local ARCH
  case "$(uname -m)" in
    x86_64|amd64) ARCH="linux-amd64";;
    aarch64|arm64) ARCH="linux-arm64";;
    *) fail "不支持的架构: $(uname -m)（仅 amd64/arm64 有 wb2api release）";;
  esac
  local DEST="$TOOLS_DIR/workbuddy2api"
  if ss -ltn 2>/dev/null | grep -q ":${WB_PORT} "; then
    ok "${WB_PORT} 已被监听，跳过安装（若为本机既有 wb2api 则无需重复部署）"
    return 0
  fi
  if [ -x "$DEST/wb2api" ]; then
    ok "$DEST/wb2api 已存在，跳过下载"
  else
    mkdir -p "$DEST"
    detail "下载 wb2api ${VER} (${ARCH}) → ${DEST}/"
    curl -fsSL --retry 3 -o /tmp/wb2api_$$.tar.gz \
      "https://github.com/${REPO}/releases/download/${VER}/wb2api-panel-${VER}-${ARCH}.tar.gz" \
      || fail "下载 wb2api 失败"
    tar xzf /tmp/wb2api_$$.tar.gz -C "$DEST"
    rm -f /tmp/wb2api_$$.tar.gz
    [ -x "$DEST/wb2api" ] || fail "解包后未找到 wb2api 可执行文件"
  fi
  # 配置：listen 7863 + 随机 api_key
  local CFG="$DEST/config.json"
  if [ ! -f "$CFG" ]; then
    if [ -f "$DEST/config.example.json" ]; then cp "$DEST/config.example.json" "$CFG"; fi
    python3 - "$CFG" "$WB_PORT" <<'PY'
import json, pathlib, secrets, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text()) if p.exists() else {}
d["listen"] = ":" + sys.argv[2]
d["api_key"] = "aam-" + secrets.token_hex(16)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2))
print("config.json 已生成, api_key 前缀 aam-")
PY
    echo "    api_key 已随机生成: $(grep -o '"api_key": *"[^"]*"' "$CFG")"
    echo "    （AAM 面板「设置」→ WorkBuddy 网关 API Key 填同一值）"
  fi
  install_systemd workbuddy2api \
    "WorkBuddy2api (腾讯CodeBuddy上游网关 7863)" \
    "$DEST" "$(cd "$DEST" && pwd)/wb2api run"
  detail "健康检查 WorkBuddy"
  sleep 2
  curl -fsS --retry 5 --retry-delay 2 "http://127.0.0.1:${WB_PORT}/healthz" 2>/dev/null || true
  echo
  ok "WorkBuddy 网关就绪: http://127.0.0.1:${WB_PORT}/panel/ （AAM 面板里 WorkBuddy 授权/任务会自动走它）"
}

############################## Trae 网关 (trae2api 8770) ##############################
install_trae() {
  detail "Trae 网关 (trae2api)"
  need git "apt install -y git"
  local SRC="${TRAE2API_SRC:-https://github.com/autumnsentiment/Trae2api-cn.git}"
  local DEST="$TOOLS_DIR/trae2api"
  if ss -ltn 2>/dev/null | grep -q ":${TRAE_PORT} "; then
    ok "${TRAE_PORT} 已被监听，跳过安装（若为本机既有 trae2api 则无需重复部署）"
    return 0
  fi
  if [ -f "$DEST/README.md" ]; then
    ok "$DEST 已存在，跳过 clone"
  elif [ -n "${TRAE2API_LOCAL:-}" ]; then
    detail "从本地目录复制 ${TRAE2API_LOCAL}"
    cp -a "$TRAE2API_LOCAL" "$DEST"
  else
    detail "clone trae2api → ${DEST}/"
    git clone --depth 1 "$SRC" "$DEST" >/dev/null 2>&1 || fail "clone trae2api 失败($SRC 需可访问)"
  fi
  cd "$DEST"
  if [ ! -d venv ]; then
    detail "创建 venv 并安装依赖（trae2api 依赖版本较新,建议 Python 3.11+）"
    python3 -m venv venv
    ./venv/bin/pip install -q --upgrade pip
    ./venv/bin/pip install -q -r requirements.txt || fail "trae2api 依赖安装失败（Python 版本过低? 需要 3.11+）"
  fi
  install_systemd trae2api \
    "Trae2api (字节 Trae 上游网关 8770)" \
    "$DEST" "$(cd "$DEST" && pwd)/venv/bin/uvicorn src.main:app --host 0.0.0.0 --port ${TRAE_PORT}"
  detail "健康检查 Trae"
  sleep 2
  curl -fsS --retry 5 --retry-delay 2 "http://127.0.0.1:${TRAE_PORT}/healthz" 2>/dev/null || true
  echo
  ok "Trae 网关就绪: http://127.0.0.1:${TRAE_PORT}/ （AAM 面板 Trae 签到/对话会自动走它）"
}

install_systemd() {
  local name="$1" desc="$2" dir="$3" exec="$4"
  if systemctl is-active --quiet "$name" 2>/dev/null; then
    ok "systemd ${name} 已存在且运行中，跳过覆盖（保留现有实例）"
    return 0
  fi
  if [ "${AAM_SKIP_SYSTEMD:-0}" = "1" ]; then
    detail "跳过 systemd，前台启动 ${name}（Ctrl-C 退出）"
    (cd "$dir" && exec $exec)
    return 0
  fi
  if [ "$(id -u)" != "0" ]; then
    ok "非 root，跳过 systemd（手工启动: cd $dir && $exec）"
    return 0
  fi
  local unit="/etc/systemd/system/${name}.service"
  cat > "$unit" <<EOF
[Unit]
Description=$desc
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$dir
ExecStart=$exec
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$name" >/dev/null 2>&1 || systemctl restart "$name"
  systemctl is-active --quiet "$name" && ok "systemd ${name} 已启动并开机自启" || fail "systemd ${name} 启动失败, 看 journalctl -u ${name}"
}

ALL="${1:-all}"
case "$ALL" in
  all) install_workbuddy; install_trae;;
  workbuddy|wb) install_workbuddy;;
  trae) install_trae;;
  *) echo "用法: bash deploy-gateways.sh [all|workbuddy|trae]"; exit 1;;
esac

echo ""
echo "==> 可选网关部署完成。AAM 面板地址不变；回面板操作对应平台即可。"
echo "    卸载: systemctl disable --now workbuddy2api trae2api"