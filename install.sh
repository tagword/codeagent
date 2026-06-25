#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# CodeAgent — 一键安装脚本
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/tagword/codeagent/main/install.sh | bash
#   或本地: bash install.sh
#
# 自动检测国内网络环境，使用 PyPI 镜像加速（如清华源）
# 幂等设计：多次运行安全，中断后重跑可继续
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── 颜色 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}▶${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; exit 1; }

# ── 辅助函数 ─────────────────────────────────────────────────────────
# 安全克隆：自动检测默认分支，支持超时和重试
git_clone_safe() {
  local repo="$1" dest="$2"
  local attempts=0 max=2
  while [ $attempts -lt $max ]; do
    attempts=$((attempts + 1))
    info "  git clone $repo（尝试 $attempts/$max）..."
    if timeout 45 git clone --depth 1 "https://github.com/tagword/${repo}.git" "$dest"; then
      # 验证克隆结果——目录非空且有 Python 文件
      if [ -f "$dest/pyproject.toml" ] || [ -f "$dest/setup.py" ] || [ -f "$dest/setup.cfg" ]; then
        return 0
      fi
      warn "  $repo 克隆不完整，重试..."
      rm -rf "$dest"
    else
      warn "  git clone $repo 超时或失败，重试..."
    fi
    [ $attempts -lt $max ] && sleep 2
  done
  return 1
}

# 安全下载：检查 HTTP 状态和文件有效性
curl_tarball_safe() {
  local repo="$1" dest_tgz="$2"
  local attempts=0 max=2
  while [ $attempts -lt $max ]; do
    attempts=$((attempts + 1))
    info "  curl tarball $repo（尝试 $attempts/$max）..."
    # -f = 4xx/5xx 时退出非零；-L = 跟随重定向；--connect-timeout=15；--max-time=60
    if curl -fL --connect-timeout 15 --max-time 60 \
      "https://github.com/tagword/${repo}/tarball/HEAD" \
      -o "$dest_tgz"; then
      # 验证：文件 > 100 字节且是 gzip 格式
      if [ -s "$dest_tgz" ] && [ "$(head -c 2 "$dest_tgz")" = $'\x1f\x8b' ]; then
        return 0
      fi
      local fsize
      fsize=$([ -f "$dest_tgz" ] && wc -c < "$dest_tgz" || echo 0)
      warn "  $repo tarball 无效（${fsize} bytes），重试..."
    fi
    rm -f "$dest_tgz"
    [ $attempts -lt $max ] && sleep 2
  done
  return 1
}

# 安装一个 seed 包（先克隆，克隆失败则降级到 tarball）
install_seed_pkg() {
  local pkg="$1"
  local src_dir="$SEED_SRC/$pkg"
  local tgz_path="$SEED_SRC/${pkg}.tar.gz"

  # 跳过已安装的（idempotent）
  if python -c "import $pkg" 2>/dev/null; then
    ok "  $pkg 已安装，跳过"
    return 0
  fi

  info "  安装 $pkg ..."
  rm -rf "$src_dir" "$tgz_path"

  # 方案 A：git clone（自动检测分支，更可靠）
  if git_clone_safe "$pkg" "$src_dir"; then
    pip install "$src_dir" --no-input -q
    ok "  $pkg 安装完成"
    return 0
  fi

  # 方案 B：curl tarball 降级（git 协议不通时使用）
  warn "  git clone 失败，尝试 tarball 方式..."
  if curl_tarball_safe "$pkg" "$tgz_path"; then
    mkdir -p "$src_dir"
    tar xzf "$tgz_path" -C "$src_dir" --strip-components=1
    pip install "$src_dir" --no-input -q
    ok "  $pkg 安装完成（tarball）"
    return 0
  fi

  err "$pkg 安装失败，请检查网络后重试"
}

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

$USE_MIRROR && PIP_MIRROR_FLAG="-i $PIP_MIRROR_URL"

# ── 检测系统 ──────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Linux)  ;;
  Darwin) ;;
  *)      err "不支持的操作系统: $OS（仅支持 Linux / macOS）" ;;
esac
info "系统: $OS $ARCH"

# ── 检测 Python ──────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then PYTHON="$cmd"; break; fi
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

# ── 创建/进入工作目录 ────────────────────────────────────────────────
INSTALL_DIR="${CODEAGENT_DIR:-"$HOME/codeagent"}"

if [ -d "$INSTALL_DIR" ]; then
  # 已有目录：直接 cd 进去，后面会 git pull + 更新依赖
  warn "目录已存在: $INSTALL_DIR"
  cd "$INSTALL_DIR"

  # 非交互模式（curl | bash）下跳过询问，直接更新
  if [ -t 0 ]; then
    # 有 TTY：询问用户
    read -r -p "  是否更新已有安装？ [Y/n] " REPLY
    if [[ "$REPLY" =~ ^[Nn] ]]; then
      info "跳过安装。可使用: cd $INSTALL_DIR && source .venv/bin/activate && codeagent serve"
      exit 0
    fi
  else
    info "非交互模式，自动更新..."
  fi

  info "更新已有仓库..."
  git pull --ff-only 2>/dev/null || warn "git pull 失败，将继续使用已有代码"
else
  info "克隆仓库到 $INSTALL_DIR ..."
  git clone --depth 1 https://github.com/tagword/codeagent.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# ── 虚拟环境 ─────────────────────────────────────────────────────────
if [ -d .venv ]; then
  info "虚拟环境已存在，跳过创建"
else
  info "创建虚拟环境..."
  "$PYTHON" -m venv .venv
  ok "虚拟环境创建完成"
fi

# ── 激活 & 升级 pip ─────────────────────────────────────────────────
info "升级 pip..."
# source 在 set -e 下要小心：.venv/bin/activate 末尾的 $? 可能非零
set +e
source .venv/bin/activate 2>/dev/null
set -e
pip install --upgrade pip -q $PIP_MIRROR_FLAG

# ── 检查系统依赖（lxml 编译需要 libxml2/libxslt） ──────────────
# lxml 被 ddgs(duckduckgo_search) 依赖，ddgs 被 seed 依赖
info "检查系统依赖..."
SYSTEM_DEPS_OK=true
case "$(uname -s)" in
  Linux)
    # Termux
    if command -v pkg &>/dev/null; then
      # 检查 libxml2 是否已装
      if ! command -v xml2-config &>/dev/null && ! ldconfig -p 2>/dev/null | grep -q libxml2; then
        info "  检测到 Termux，安装 libxml2 libxslt..."
        pkg install -y libxml2 libxslt 2>/dev/null || warn "  系统依赖安装失败（编译 lxml 可能需要手动: pkg install libxml2 libxslt）"
      fi
    # Debian/Ubuntu
    elif command -v apt &>/dev/null; then
      if ! dpkg -l libxml2-dev 2>/dev/null | grep -q ^ii; then
        if command -v sudo &>/dev/null; then
          info "  检测到 Debian/Ubuntu，安装 libxml2-dev libxslt1-dev..."
          sudo -n apt install -y libxml2-dev libxslt1-dev 2>/dev/null || warn "  系统依赖安装失败（可手动: sudo apt install libxml2-dev libxslt1-dev）"
        else
          warn "  需要 libxml2-dev libxslt1-dev（运行: sudo apt install libxml2-dev libxslt1-dev）"
        fi
      fi
    # RHEL/Fedora/CentOS
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
    if command -v brew &>/dev/null; then
      if ! brew list libxml2 2>/dev/null | grep -q libxml2; then
        info "  检测到 macOS，安装 libxml2..."
        brew install libxml2 libxslt 2>/dev/null || warn "  libxml2 安装失败，编译 lxml 可能需要手动: brew install libxml2 libxslt"
      fi
    fi
    ;;
esac

# ── 安装私有依赖（Seed 框架） ──────────────────────────────────────
info "安装 Seed 框架（私有依赖: seed, seed-model-providers, seed-tools）..."
SEED_SRC="$INSTALL_DIR/.seed-build"
mkdir -p "$SEED_SRC"

install_seed_pkg "seed-model-providers"
install_seed_pkg "seed"
install_seed_pkg "seed-tools"

rm -rf "$SEED_SRC"
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
    $USE_MIRROR && NPM_ARGS="--registry=https://registry.npmmirror.com"
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
echo -e "  一键启动:"
echo -e "    ${CYAN}bash $INSTALL_DIR/run.sh${NC}"
echo ""
echo -e "  或手动运行:"
echo -e "    ${CYAN}source $INSTALL_DIR/.venv/bin/activate${NC}"
echo -e "    ${CYAN}codeagent serve${NC}"
echo ""
echo -e "  浏览器打开:  ${CYAN}http://localhost:8765${NC}"
echo ""
echo -e "  查看帮助:"
echo -e "    ${CYAN}codeagent --help${NC}"
echo ""
