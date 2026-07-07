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

  # ── 检查系统依赖（lxml 编译需要 libxml2/libxslt） ────────────────
  # lxml 被 ddgs(duckduckgo_search) 依赖，ddgs 被 seed 依赖
  info "检查系统依赖..."
  case "$(uname -s)" in
    Linux)
      if command -v pkg &>/dev/null; then
        # Termux（Android）— manylinux wheel 不兼容 bionic libc，需编译
        info "  检测到 Termux（Android），安装编译依赖..."
        if ! pkg install -y libxml2 libxslt clang make pkg-config ndk-sysroot 2>&1; then
          warn "  首轮安装失败，尝试更新索引后重试..."
          pkg update -y 2>&1 || true
          pkg install -y libxml2 libxslt clang make pkg-config ndk-sysroot 2>&1 || warn "  系统依赖安装失败，编译 lxml 可能报错"
        fi
      elif command -v apt &>/dev/null; then
        # Debian/Ubuntu
        if ! dpkg -l libxml2-dev 2>/dev/null | grep -q ^ii; then
          if command -v sudo &>/dev/null; then
            info "  检测到 Debian/Ubuntu，安装 libxml2-dev libxslt1-dev..."
            sudo -n apt install -y libxml2-dev libxslt1-dev 2>/dev/null || warn "  系统依赖安装失败（可手动: sudo apt install libxml2-dev libxslt1-dev）"
          else
            warn "  需要 libxml2-dev libxslt1-dev（运行: sudo apt install libxml2-dev libxslt1-dev）"
          fi
        fi
      elif command -v dnf &>/dev/null; then
        if ! rpm -q libxml2-devel 2>/dev/null | grep -q libxml2; then
          if command -v sudo &>/dev/null; then
            info "  检测到 RHEL/Fedora，安装 libxml2-devel libxslt-devel..."
            sudo -n dnf install -y libxml2-devel libxslt-devel 2>/dev/null || warn "  系统依赖安装失败（可手动: sudo dnf install libxml2-devel libxslt-devel）"
          else
            warn "  需要 libxml2-devel libxslt-devel（运行: sudo dnf install libxml2-devel libxslt-devel）"
          fi
        fi
      elif command -v yum &>/dev/null; then
        if ! rpm -q libxml2-devel 2>/dev/null | grep -q libxml2; then
          if command -v sudo &>/dev/null; then
            info "  检测到 CentOS，安装 libxml2-devel libxslt-devel..."
            sudo -n yum install -y libxml2-devel libxslt-devel 2>/dev/null || warn "  系统依赖安装失败（可手动: sudo yum install libxml2-devel libxslt-devel）"
          else
            warn "  需要 libxml2-devel libxslt-devel（运行: sudo yum install libxml2-devel libxslt-devel）"
          fi
        fi
      fi
      ;;
    Darwin)
      if command -v brew &>/dev/null && ! brew list libxml2 2>/dev/null | grep -q libxml2; then
        info "  检测到 macOS，安装 libxml2..."
        brew install libxml2 libxslt 2>/dev/null || warn "  libxml2 安装失败，可手动: brew install libxml2 libxslt"
      fi
      ;;
  esac

  # 提前安装 lxml（分离出错点，方便调试，也缓存 wheel）
  info "预装 lxml（seed 的间接依赖）..."
  pip install lxml -q $PIP_MIRROR_FLAG 2>&1 || warn "  lxml 预装失败，seed 安装时可能出错"

  # ── 安装私有依赖（Seed 框架） ──────────────────────────────────
  # pyproject.toml 已添加 git+https 依赖，pip install 可自动拉取
  # 但 run.sh 用更健壮的方式（多策略重试 + tarball 降级）优先处理
  if ! pip show seed-model-providers &>/dev/null; then
    info "安装 Seed 框架（私有依赖: seed, seed-model-providers, seed-tools）..."
    SEED_SRC="$PROJECT_ROOT/.seed-build"
    mkdir -p "$SEED_SRC"

    install_seed_pkg() {
      local pkg="$1"
      local src_dir="$SEED_SRC/$pkg"
      local tgz_path="$SEED_SRC/${pkg}.tar.gz"
      local attempts max=2

      if python -c "import $pkg" 2>/dev/null; then
        ok "  $pkg 已安装，跳过"
        return 0
      fi

      info "  安装 $pkg ..."
      rm -rf "$src_dir" "$tgz_path"

      # 方案 A：git clone（有 45 秒超时）
      attempts=0
      while [ $attempts -lt $max ]; do
        attempts=$((attempts + 1))
        info "  git clone $pkg（尝试 $attempts/$max）..."
        if timeout 45 git clone --depth 1 "https://github.com/tagword/${pkg}.git" "$src_dir"; then
          if [ -f "$src_dir/pyproject.toml" ] || [ -f "$src_dir/setup.py" ]; then
            pip install "$src_dir" --no-input -q $PIP_MIRROR_FLAG
            ok "  $pkg 安装完成"
            return 0
          fi
          warn "  $pkg 克隆不完整，重试..."
          rm -rf "$src_dir"
        else
          warn "  git clone $pkg 超时或失败，重试..."
        fi
        [ $attempts -lt $max ] && sleep 2
      done

      # 方案 B：curl tarball（有超时限制）
      attempts=0
      while [ $attempts -lt $max ]; do
        attempts=$((attempts + 1))
        info "  curl tarball $pkg（尝试 $attempts/$max）..."
        if curl -fL --connect-timeout 15 --max-time 60 \
          "https://github.com/tagword/${pkg}/tarball/HEAD" \
          -o "$tgz_path"; then
          if [ -s "$tgz_path" ] && [ "$(head -c 2 "$tgz_path")" = $'\x1f\x8b' ]; then
            mkdir -p "$src_dir"
            tar xzf "$tgz_path" -C "$src_dir" --strip-components=1
            pip install "$src_dir" --no-input -q $PIP_MIRROR_FLAG
            ok "  $pkg 安装完成（tarball）"
            return 0
          fi
          warn "  $pkg tarball 无效，重试..."
        fi
        rm -f "$tgz_path"
        [ $attempts -lt $max ] && sleep 2
      done
      err "$pkg 安装失败，请检查网络后重试"
    }

    install_seed_pkg "seed-model-providers"
    install_seed_pkg "seed"
    install_seed_pkg "seed-tools"
    rm -rf "$SEED_SRC"
    ok "Seed 框架安装完成"
  fi

  # ── 安装 CodeAgent ──────────────────────────────────────────────
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
echo ""
echo -e "${BLUE}━━━ 🚀 启动 CodeAgent Web UI ━━━${NC}"
echo -e "  监听地址:  ${CYAN}http://$HOST:$PORT${NC}"
echo -e "  浏览器打开: ${GREEN}http://localhost:$PORT${NC}"
echo -e "  按 ${YELLOW}Ctrl+C${NC} 停止服务"
echo ""

# 确保虚拟环境激活
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
  source "$PROJECT_ROOT/.venv/bin/activate"
fi

# 启动服务
exec codeagent serve --host "$HOST" --port "$PORT"
