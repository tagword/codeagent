#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# CodeAgent — 一键安装脚本
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/tagword/codeagent/main/install.sh | bash
#   或本地: bash install.sh
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── 颜色 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; NC='\033[0m' # No Color
info()  { echo -e "${CYAN}▶${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; exit 1; }

# ── 检测系统 ──────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Linux)  ;;
  Darwin) ;;
  *)      err "不支持的操作系统: $OS (仅支持 Linux / macOS)" ;;
esac
info "系统: $OS $ARCH"

# ── 检测 Python ──────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done
[ -z "$PYTHON" ] && err "未检测到 Python，请先安装 Python ≥3.9"

PY_VER="$($PYTHON --version 2>&1 | awk '{print $2}')"
PY_MAJOR="$($PYTHON -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$($PYTHON -c 'import sys; print(sys.version_info.minor)')"
[ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; } && err "Python 版本过低: $PY_VER（需要 ≥3.9）"
ok "Python $PY_VER"

# ── 检测 Git ─────────────────────────────────────────────────────────
command -v git &>/dev/null || err "未检测到 Git，请先安装 Git"
ok "Git $(git --version | awk '{print $3}')"

# ── 选择安装方式 ─────────────────────────────────────────────────────
INSTALL_DIR="${CODEGEANT_DIR:-"$HOME/codeagent"}"

if [ -d "$INSTALL_DIR" ]; then
  warn "目录已存在: $INSTALL_DIR"
  read -r -p "  是否更新已有安装？ [Y/n] " REPLY
  if [[ "$REPLY" =~ ^[Nn] ]]; then
    info "跳过安装。可使用: cd $INSTALL_DIR && git pull && source .venv/bin/activate && codeagent serve"
    exit 0
  fi
  info "更新已有仓库..."
  cd "$INSTALL_DIR"
  git pull --ff-only || warn "git pull 失败，将尝试重新克隆..."
  if [ -d .venv ]; then
    info "虚拟环境已存在，跳过创建"
    SKIP_VENV=1
  fi
else
  info "克隆仓库到 $INSTALL_DIR ..."
  git clone --depth 1 https://github.com/tagword/codeagent.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# ── 创建虚拟环境 ─────────────────────────────────────────────────────
if [ "${SKIP_VENV:-0}" != "1" ]; then
  info "创建虚拟环境..."
  "$PYTHON" -m venv .venv
  ok "虚拟环境创建完成"
fi

# ── 激活 & 升级 pip ─────────────────────────────────────────────────
info "升级 pip..."
source .venv/bin/activate
pip install --upgrade pip -q

# ── 安装 CodeAgent ──────────────────────────────────────────────────
info "安装 CodeAgent（默认包含 Starlette + Uvicorn + APScheduler）..."
pip install -e . -q
ok "CodeAgent 安装完成"

# ── 可选: npm 前端构建 ──────────────────────────────────────────────
WEBUI_DIR="$INSTALL_DIR/codeagent/webui"
if [ -f "$WEBUI_DIR/package.json" ] && [ ! -d "$WEBUI_DIR/dist" ]; then
  if command -v node &>/dev/null; then
    info "构建 Web UI 前端..."
    cd "$WEBUI_DIR"
    npm install --silent 2>/dev/null && npm run build 2>/dev/null && ok "Web UI 构建完成" || warn "Web UI 构建跳过（可稍后手动构建）"
    cd "$INSTALL_DIR"
  else
    warn "未检测到 Node.js，Web UI 前端使用 CDN 模式也能正常运行"
  fi
fi

# ── 完成 ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  CodeAgent 安装成功！${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  激活虚拟环境:"
echo -e "    ${CYAN}source $INSTALL_DIR/.venv/bin/activate${NC}"
echo ""
echo -e "  启动 Web UI:"
echo -e "    ${CYAN}codeagent serve${NC}"
echo ""
echo -e "  浏览器打开:  ${CYAN}http://localhost:8765${NC}"
echo ""
echo -e "  查看帮助:"
echo -e "    ${CYAN}codeagent --help${NC}"
echo ""
