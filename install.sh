#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# CodeAgent — 一键安装脚本
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/tagword/codeagent/main/install.sh | bash
#   或本地: bash install.sh
#
# 自动检测国内网络环境，使用 PyPI 镜像加速（如清华源）
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── 颜色 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; NC='\033[0m' # No Color
info()  { echo -e "${CYAN}▶${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; exit 1; }

# ── 国内镜像检测 ──────────────────────────────────────────────────────
USE_MIRROR=false
PIP_MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
PIP_MIRROR_FLAG=""

info "检测网络环境..."
if command -v curl &>/dev/null; then
  if curl -s --connect-timeout 3 -o /dev/null --max-time 5 https://pypi.org/simple/ 2>/dev/null; then
    ok "直连 PyPI 正常"
  elif curl -s --connect-timeout 2 -o /dev/null --max-time 3 https://www.baidu.com 2>/dev/null; then
    USE_MIRROR=true
    ok "检测到国内网络 → 使用镜像: $PIP_MIRROR_URL"
  else
    warn "网络似乎不可达，继续直连尝试"
  fi
elif command -v wget &>/dev/null; then
  if wget -q --timeout=5 -O /dev/null https://pypi.org/simple/ 2>/dev/null; then
    ok "直连 PyPI 正常"
  else
    USE_MIRROR=true
    warn "检测到国内网络 → 使用镜像: $PIP_MIRROR_URL"
  fi
else
  warn "未检测到 curl 或 wget，跳过网络检测"
fi

if $USE_MIRROR; then
  PIP_MIRROR_FLAG="-i $PIP_MIRROR_URL"
fi

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
pip install --upgrade pip -q $PIP_MIRROR_FLAG

# ── 安装私有依赖（Seed 框架） ──────────────────────────────────────
info "安装 Seed 框架（私有依赖: seed, seed-model-providers, seed-tools）..."
SEED_GIT_BASE="https://github.com/tagword"
SEED_TMPDIR="$(mktemp -d /tmp/codeagent-seed-XXXXXX)"

# 安装顺序: seed-model-providers → seed → seed-tools（依赖链）
# 用 git clone --depth 1 代替 pip install git+https://，避免全量拉取历史
for PKG in seed-model-providers seed seed-tools; do
  SRC="$SEED_TMPDIR/$PKG"
  info "  拉取 $PKG ..."
  git clone --depth 1 --progress "${SEED_GIT_BASE}/${PKG}.git" "$SRC"
  pip install -e "$SRC" $PIP_MIRROR_FLAG -q
  ok "  $PKG 安装完成"
done
rm -rf "$SEED_TMPDIR"
ok "Seed 框架安装完成"

# ── 安装 CodeAgent ──────────────────────────────────────────────────
info "安装 CodeAgent（默认包含 Starlette + Uvicorn + 代码检测/审计工具）..."
pip install -e . $PIP_MIRROR_FLAG -q
ok "CodeAgent 安装完成"

# ── 可选: npm 前端构建 ──────────────────────────────────────────────
WEBUI_DIR="$INSTALL_DIR/webui-v2"
if [ -f "$WEBUI_DIR/package.json" ] && [ ! -d "$WEBUI_DIR/dist" ]; then
  if command -v node &>/dev/null; then
    info "构建 Web UI 前端..."
    cd "$WEBUI_DIR"
    NPM_ARGS=""
    if $USE_MIRROR; then
      CURRENT_REGISTRY=$(npm config get registry 2>/dev/null || echo "")
      if [[ "$CURRENT_REGISTRY" != *"taobao"* ]] && [[ "$CURRENT_REGISTRY" != *"npmmirror"* ]]; then
        NPM_ARGS="--registry=https://registry.npmmirror.com"
      fi
    fi
    npm install --silent $NPM_ARGS 2>/dev/null && npm run build 2>/dev/null && ok "Web UI 构建完成" || warn "Web UI 构建跳过（可稍后手动构建）"
    cd "$INSTALL_DIR"
  else
    warn "未检测到 Node.js，Web UI v2 前端跳过构建（将使用内置 UI 兜底）"
  fi
fi

# ── 完成 ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  CodeAgent 安装成功！${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  一键运行:"
echo -e "    ${CYAN}bash $INSTALL_DIR/run.sh${NC}"
echo ""
echo -e "  或手动激活:"
echo -e "    ${CYAN}source $INSTALL_DIR/.venv/bin/activate${NC}"
echo -e "    ${CYAN}codeagent serve${NC}"
echo ""
echo -e "  浏览器打开:  ${CYAN}http://localhost:8765${NC}"
echo ""
echo -e "  查看帮助:"
echo -e "    ${CYAN}codeagent --help${NC}"
echo ""
