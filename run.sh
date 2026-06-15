#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# CodeAgent — 一键运行脚本
# 用法:
#   bash run.sh                  # 首次自动安装，然后启动
#   bash run.sh --no-install     # 仅启动（跳过安装检查）
#   bash run.sh --port 8766      # 指定端口
#   bash run.sh --host 0.0.0.0   # 指定监听地址
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── 颜色 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${CYAN}▶${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; exit 1; }
title() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

# ── 参数解析 ──────────────────────────────────────────────────────────
SKIP_INSTALL=false
PORT=8765
HOST="0.0.0.0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install) SKIP_INSTALL=true; shift ;;
    --port) PORT="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    *) err "未知参数: $1（用法: bash run.sh [--no-install] [--port 8765] [--host 0.0.0.0]）" ;;
  esac
done

# ── 脚本所在目录（项目根目录）─────────────────────────────────────────
cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"
info "项目目录: $PROJECT_ROOT"

# ── 国内镜像检测 ──────────────────────────────────────────────────────
USE_MIRROR=false
PIP_MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
PIP_MIRROR_FLAG=""

title "🌐 网络检测"

# 快速检测：尝试访问 pypi.org（超时 3 秒）
if command -v curl &>/dev/null; then
  if curl -s --connect-timeout 3 -o /dev/null --max-time 5 https://pypi.org/simple/ 2>/dev/null; then
    ok "直连 PyPI 正常"
  else
    warn "直连 PyPI 超时，检测到可能为国内网络环境"
    # 再确认一下：能访问百度但访问不了 pypi.org → 国内环境
    if curl -s --connect-timeout 2 -o /dev/null --max-time 3 https://www.baidu.com 2>/dev/null; then
      USE_MIRROR=true
      ok "检测到国内网络 → 使用镜像: $PIP_MIRROR_URL"
    else
      # 可能完全没网，留给后续安装报错
      warn "网络似乎不可达，将尝试直连，如有失败请检查网络"
    fi
  fi
elif command -v wget &>/dev/null; then
  if wget -q --timeout=5 -O /dev/null https://pypi.org/simple/ 2>/dev/null; then
    ok "直连 PyPI 正常"
  else
    USE_MIRROR=true
    ok "检测到国内网络 → 使用镜像: $PIP_MIRROR_URL"
  fi
else
  warn "未检测到 curl 或 wget，跳过网络检测"
fi

if $USE_MIRROR; then
  PIP_MIRROR_FLAG="-i $PIP_MIRROR_URL"
fi

# ── 安装阶段 ──────────────────────────────────────────────────────────
if ! $SKIP_INSTALL; then
  title "🔧 环境检查"

  # Python 检测
  PYTHON=""
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      PYTHON="$cmd"
      break
    fi
  done
  [ -z "$PYTHON" ] && err "未检测到 Python，请先安装 Python ≥ 3.9"

  PY_VER="$($PYTHON --version 2>&1 | awk '{print $2}')"
  PY_MAJOR="$($PYTHON -c 'import sys; print(sys.version_info.major)')"
  PY_MINOR="$($PYTHON -c 'import sys; print(sys.version_info.minor)')"
  [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; } \
    && err "Python 版本过低: $PY_VER（需要 ≥ 3.9）"
  ok "Python $PY_VER"

  # Git 检测
  command -v git &>/dev/null || err "未检测到 Git，请先安装 Git"
  ok "Git $(git --version | awk '{print $3}')"

  # ── 虚拟环境 ──────────────────────────────────────────────────────
  VENV_DIR="$PROJECT_ROOT/.venv"
  if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    ok "虚拟环境已存在: $VENV_DIR"
  else
    title "📦 创建虚拟环境"
    info "正在创建虚拟环境..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "虚拟环境创建完成"
  fi

  # ── 激活 & 安装 ──────────────────────────────────────────────────
  title "📥 安装依赖"
  source "$VENV_DIR/bin/activate"

  # 升级 pip
  info "升级 pip..."
  pip install --upgrade pip -q $PIP_MIRROR_FLAG

  # 检查是否已安装（粗略判断）
  if pip show codeagent &>/dev/null; then
    ok "CodeAgent 已安装，跳过"
  else
    info "安装 CodeAgent（含 Starlette + Uvicorn + 代码检测/审计工具）..."
    pip install -e . $PIP_MIRROR_FLAG -q
    ok "CodeAgent 安装完成"
  fi

  # ── Web UI v2 前端构建（如需要）──────────────────────────────────
  WEBUI_V2_DIR="$PROJECT_ROOT/webui-v2"
  if [ -f "$WEBUI_V2_DIR/package.json" ] && [ ! -d "$WEBUI_V2_DIR/dist" ]; then
    if command -v node &>/dev/null; then
      title "🏗️  构建 Web UI 前端"
      info "检测到 webui-v2 前端未构建，正在构建..."
      cd "$WEBUI_V2_DIR"
      # npm install 也可用国内镜像
      NPM_ARGS=""
      if $USE_MIRROR; then
        # 检查是否已配过镜像 registry
        CURRENT_REGISTRY=$(npm config get registry 2>/dev/null || echo "")
        if [[ "$CURRENT_REGISTRY" != *"taobao"* ]] && [[ "$CURRENT_REGISTRY" != *"npmmirror"* ]]; then
          NPM_ARGS="--registry=https://registry.npmmirror.com"
        fi
      fi
      npm install --silent $NPM_ARGS 2>/dev/null
      npm run build 2>/dev/null
      ok "Web UI 前端构建完成"
      cd "$PROJECT_ROOT"
    else
      warn "未检测到 Node.js，Web UI v2 前端跳过构建（将使用内置 UI 兜底）"
    fi
  fi

  # ── 环境初始化 ──────────────────────────────────────────────────
  if [ ! -f "$PROJECT_ROOT/config/env" ]; then
    title "📝 首次初始化"
    info "未检测到 config/env 配置文件，正在初始化..."
    # 尝试自动初始化，失败也不阻断
    source "$VENV_DIR/bin/activate"
    codeagent config init 2>/dev/null || true
    echo -e "${YELLOW}  请编辑 $PROJECT_ROOT/config/env 配置你的 LLM API Key${NC}"
    echo -e "${YELLOW}  也可参考 $PROJECT_ROOT/config/env.example${NC}"
  fi
fi

# ── 启动 ────────────────────────────────────────────────────────────
title "🚀 启动 CodeAgent Web UI"
info "监听地址: http://$HOST:$PORT"
echo -e "${GREEN}  浏览器打开: http://localhost:$PORT${NC}"
info "按 Ctrl+C 停止服务"
echo ""

# 确保虚拟环境激活
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
  source "$PROJECT_ROOT/.venv/bin/activate"
fi

# 启动服务
exec codeagent serve --host "$HOST" --port "$PORT"
