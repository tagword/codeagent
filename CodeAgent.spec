# -*- mode: python ; coding: utf-8 -*-
"""
CodeAgent macOS .app — 使用方式: pyinstaller CodeAgent.spec
"""
import os
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F405 — PyInstaller 注入变量

# ── 隐式导入 ─────────────────────────────────────────────
_hiddenimports = [
    # uvicorn 动态加载的模块
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

# ── 排除（精简体积） ──────────────────────────────────────
_excludes = [
    "tkinter",
    "test",
    "unittest",
    "distutils",
    "setuptools",
    "pip",
]

# ── WebUI 静态资源 ────────────────────────────────────────
_webui_datas = [
    (str(p), "codeagent/webui")
    for p in sorted((ROOT / "codeagent" / "webui").rglob("*"))
    if p.is_file()
]

# ── 项目根目录文件（包含 tray_icon.png） ──────────────────
_top_datas = []
for p in (ROOT / "codeagent").iterdir():
    if p.is_file() and p.suffix in {".html", ".css", ".js"}:
        _top_datas.append((str(p), "codeagent"))
# 菜单栏图标
for _tray_name in ("tray_icon.png", "tray_icon@2x.png"):
    _tray_path = ROOT / _tray_name
    if _tray_path.exists():
        _top_datas.append((str(_tray_path), "."))

_datas = _webui_datas + _top_datas

# ── Analysis ─────────────────────────────────────────────
a = Analysis(
    ["package_launcher.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ── 可执行文件 ───────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CodeAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["codeagent.icns"],
)

# ── 收集依赖 ─────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CodeAgent",
)

# ── macOS .app ──────────────────────────────────────────
app = BUNDLE(
    coll,
    name="CodeAgent.app",
    icon="codeagent.icns",
    bundle_identifier="com.codeagent.app",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "CFBundleDisplayName": "CodeAgent",
        "CFBundleName": "CodeAgent",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "© 2025 CodeAgent",
    },
)
