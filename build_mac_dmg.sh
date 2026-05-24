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

# Bundle & link for macOS 12 Monterey (incl. 12.7.6)
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"

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

VENV="$ROOT/.build-venv"
DIST="$ROOT/dist"
APP="$DIST/CodeAgent.app"
DMG="$DIST/CodeAgent-mac.dmg"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " CodeAgent macOS DMG build"
echo " Python: $($PYTHON --version 2>&1)"
echo " Root:   $ROOT"
echo " Target: macOS ${MACOSX_DEPLOYMENT_TARGET}+"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_check_python_supports_macos12 "$PYTHON"

# ── 1. Virtualenv ─────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "==> Create build venv"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
export VIRTUAL_ENV="$VENV"

echo "==> Upgrade pip"
python -m pip install --upgrade pip -q

# ── 2. Install packages (monorepo siblings or PyPI) ─────────────────────
echo "==> Install seed / seed-tools / codeagent"
if [ -d "$MONO/seed/pyproject.toml" ] && [ -d "$MONO/seed-tools/pyproject.toml" ]; then
  pip install -e "$MONO/seed"
  pip install -e "$MONO/seed-tools[code]"
  pip install -e "$ROOT"
else
  pip install -e "$ROOT[dev,bundle]"
fi

echo "==> Install build deps"
pip install pyinstaller pillow rumps -q

# ── 3. Stage external CLI tools ───────────────────────────────────────
echo "==> Stage bundled tools (git, node, eslint, ast-grep, …)"
python "$ROOT/prepare_bundle_tools.py"

# ── 4. Icons ──────────────────────────────────────────────────────────
if [ -f "$ROOT/icon.png" ]; then
  echo "==> Generate .icns + tray icons"
  python "$ROOT/make_icon.py"
else
  echo "⚠ icon.png missing — skipping icon generation"
fi

# ── 5. PyInstaller ────────────────────────────────────────────────────
echo "==> PyInstaller"
rm -rf "$DIST/CodeAgent" "$APP"
pyinstaller "$ROOT/CodeAgent.spec" -y --distpath "$DIST" --workpath "$ROOT/build/pyinstaller" --clean

[ -d "$APP" ] || { echo "✗ CodeAgent.app not produced"; exit 1; }

# ── 6. DMG ────────────────────────────────────────────────────────────
echo "==> Create DMG"
bash "$ROOT/make_dmg.sh"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✅ Done"
echo " App: $APP"
echo " DMG: $DMG"
echo ""
echo " Bundled tools: git, node, npm, eslint, ast-grep (+ ruff for Python scripts)"
echo " Minimum macOS: ${MACOSX_DEPLOYMENT_TARGET} (incl. Monterey 12.7.6 with python.org build)"
echo " For 微信小游戏: open UI → 工作区指向小游戏项目 → 用微信开发者工具预览"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
