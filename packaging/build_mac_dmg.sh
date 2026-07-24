#!/usr/bin/env bash
# Build CodeAgent macOS .app + DMG with bundled dev tools for WeChat mini program game dev
#
# Usage (from monorepo root or codeagent/):
#   bash codeagent/build_mac_dmg.sh
#   cd codeagent && bash build_mac_dmg.sh
#
# Requires: macOS, Python 3.11+ (推荐 python.org 安装包以兼容 macOS 12.7+),
#           Xcode CLT (for git), network (ast-grep / node download)
#
# macOS 12.7.6 (Monterey): 请用 python.org 的 Python 3.11 构建，勿用 Homebrew Python
#   下载: https://www.python.org/downloads/macos/
#   或: CODEAGENT_BUILD_PYTHON=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 bash build_mac_dmg.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
MONO="$(cd "$ROOT/.." && pwd)"
GITHUB_ORG="${CODEAGENT_GITHUB_ORG:-tagword}"

# Bundle & link for macOS 12 Monterey (incl. 12.7.6)
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"

_ensure_mono_repo() {
  local name="$1"
  local dir="$MONO/$name"
  if [ -f "$dir/pyproject.toml" ]; then
    return 0
  fi
  command -v git &>/dev/null || { echo "✗ git required to clone $name"; exit 1; }
  echo "==> Clone $name (missing at $dir)"
  git clone --depth 1 "https://github.com/${GITHUB_ORG}/${name}.git" "$dir"
}

_resolve_build_python() {
  if [ -n "${CODEAGENT_BUILD_PYTHON:-}" ]; then
    echo "$CODEAGENT_BUILD_PYTHON"
    return
  fi
  local c
  for c in \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
    "/usr/local/bin/python3.11" \
    "python3.11" \
    "python3"
  do
    if [ -x "$c" ] || command -v "$c" &>/dev/null; then
      echo "$c"
      return
    fi
  done
}

_check_python_supports_macos12() {
  local py="$1"
  local lib
  lib="$("$py" -c "
import sys
from pathlib import Path
base = Path(sys.base_prefix)
for name in ('Python', 'libpython3.11.dylib'):
    for p in [base / name, *base.glob(f'**/Versions/*/Python')]:
        if p.is_file():
            print(p)
            raise SystemExit
for p in base.rglob('libpython3.*.dylib'):
    if p.is_file():
        print(p)
        break
" 2>/dev/null || true)"
  [ -n "$lib" ] || return 0
  local minos
  minos="$(otool -l "$lib" 2>/dev/null | awk '/LC_BUILD_VERSION/{getline; getline; getline; print $2; exit}')"
  [ -n "$minos" ] || return 0
  if awk -v m="$minos" -v t="12.0" 'BEGIN{exit !(m>t)}'; then
    echo ""
    echo "⚠  当前 Python 最低系统版本为 macOS ${minos}，打出的 DMG 无法在 macOS 12.7.6 上运行。"
    echo "   请安装 python.org Python 3.11 后重建（并删除 .build-venv）："
    echo "   https://www.python.org/downloads/macos/"
    echo "   CODEAGENT_BUILD_PYTHON=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 bash build_mac_dmg.sh"
    echo ""
    if [ "${CODEAGENT_ALLOW_OLD_MAC_BUILD:-0}" != "1" ]; then
      exit 1
    fi
  else
    echo "   Python 兼容 macOS ≥ ${minos}（目标 ≥ 12.0）"
  fi
}

PYTHON="$(_resolve_build_python || true)"
[ -n "$PYTHON" ] || { echo "✗ Python 3.11+ required"; exit 1; }

NATIVE_ARCH="$(uname -m)"
case "${CODEAGENT_BUILD_ARCH:-$NATIVE_ARCH}" in
  arm64|aarch64) BUILD_ARCH=arm64 ;;
  x86_64|amd64) BUILD_ARCH=x86_64 ;;
  *) echo "✗ Unsupported CODEAGENT_BUILD_ARCH (use arm64 or x86_64)"; exit 1 ;;
esac

_run_arch() {
  if [ "$BUILD_ARCH" = "$NATIVE_ARCH" ]; then
    "$@"
  else
    arch -"$BUILD_ARCH" "$@"
  fi
}

VENV="$MONO/.build-venv-${BUILD_ARCH}"
DIST="$MONO/dist"
APP="$DIST/CodeAgent.app"
DMG="$DIST/CodeAgent-mac-${BUILD_ARCH}.dmg"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " CodeAgent macOS DMG build"
echo " Python: $(_run_arch "$PYTHON" --version 2>&1)"
echo " Arch:   ${BUILD_ARCH} (native: ${NATIVE_ARCH})"
echo " Root:   $ROOT"
echo " Target: macOS ${MACOSX_DEPLOYMENT_TARGET}+"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_check_python_supports_macos12 "$PYTHON"

# ── 1. Virtualenv ─────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "==> Create build venv (${BUILD_ARCH})"
  _run_arch "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
export VIRTUAL_ENV="$VENV"
export CODEAGENT_BUNDLE_ARCH="$BUILD_ARCH"

echo "==> Upgrade pip"
_run_arch python -m pip install --upgrade pip -q

# ── 2. Install packages (monorepo siblings; auto-clone from GitHub if missing) ─
echo "==> Ensure monorepo siblings (seed-model-providers / seed / seed-tools)"
_ensure_mono_repo seed-model-providers
_ensure_mono_repo seed
_ensure_mono_repo seed-tools

echo "==> Install seed-model-providers / seed / seed-tools / codeagent"
_run_arch pip install \
  -e "$MONO/seed-model-providers" \
  -e "$MONO/seed" \
  -e "$MONO/seed-tools[code]" \
  -e "$MONO"

echo "==> Install build deps"
_run_arch pip install pyinstaller pillow rumps -q

# ── 3. Stage external CLI tools ───────────────────────────────────────
echo "==> Stage bundled tools (git, node, eslint, ast-grep, …)"
_run_arch python "$ROOT/prepare_bundle_tools.py"

# ── 4. Icons ──────────────────────────────────────────────────────────
if [ -f "$MONO/assets/icon.png" ]; then
  echo "==> Generate .icns + tray icons"
  _run_arch python "$ROOT/make_icon.py"
else
  echo "⚠ icon.png missing — skipping icon generation"
fi

# ── 5. PyInstaller ────────────────────────────────────────────────────
echo "==> PyInstaller"
rm -rf "$DIST/CodeAgent" "$APP"
_run_arch pyinstaller "$ROOT/CodeAgent.spec" -y --distpath "$DIST" --workpath "$MONO/build/pyinstaller-${BUILD_ARCH}" --clean

[ -d "$APP" ] || { echo "✗ CodeAgent.app not produced"; exit 1; }

# ── 6. DMG ────────────────────────────────────────────────────────────
echo "==> Create DMG"
CODEAGENT_DMG_OUTPUT="$DMG" bash "$ROOT/make_dmg.sh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✅ Done"
echo " App: $APP"
echo " DMG: $DMG"
echo ""
echo " Bundled tools: git, node, npm, eslint, ast-grep (+ ruff for Python scripts)"
echo " Minimum macOS: ${MACOSX_DEPLOYMENT_TARGET} (incl. Monterey 12.7.6 with python.org build)"
echo " CPU arch: ${BUILD_ARCH}  (Intel Mac 12.x 请用 x86_64 包，Apple 芯片用 arm64 包)"
echo " For 微信小游戏: open UI → 工作区指向小游戏项目 → 用微信开发者工具预览"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
