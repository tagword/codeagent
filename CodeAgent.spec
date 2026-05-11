# -*- mode: python ; coding: utf-8 -*-
"""
CodeAgent PyInstaller Spec — macOS .app + DMG

Build:
    pyinstaller CodeAgent.spec
"""
import os
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F405 — 由 PyInstaller 注入

# ── 隐式导入 ─────────────────────────────────────────────
_hidden = [
    # CodeAgent 核心
    "codeagent.server",
    "codeagent.tools",
    "codeagent.hooks",
    "codeagent.llm",
    "codeagent.memory",
    "codeagent.agent",
    "codeagent.webui",
    "codeagent.webui.setup",
    # uvicorn 动态加载子模块
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # 菜单栏
    "rumps",
    # PIL (PyInstaller 可能漏)
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFilter",
]

# ── 排除项 ───────────────────────────────────────────────
_excludes = [
    "tkinter",
    "test",
    "unittest",
    "distutils",
    "setuptools",
    "pip",
    "email",
    "http.cookiejar",
    "http.cookies",
]

# ── 数据文件 ─────────────────────────────────────────────
webui_root = ROOT / "codeagent" / "webui"
_webui = [
    (str(p), "codeagent/webui")
    for p in sorted(webui_root.rglob("*"))
    if p.is_file()
]

_top = [
    (str(p), "codeagent")
    for p in (ROOT / "codeagent").iterdir()
    if p.is_file() and p.suffix in {".html", ".css", ".js"}
]

_dat = _webui + _top + [
    (str(ROOT / "tray_icon.png"), "."),
    (str(ROOT / "icon.png"), "."),
    (str(ROOT / "codeagent.icns"), "."),
]

# ────────────────────────────────────────────────────────
a = Analysis(
    ["package_launcher.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_dat,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    exclude_binaries=True,
    name="CodeAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,    # ← 不弹终端
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["codeagent.icns"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CodeAgent",
)

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
        "LSUIElement": True,  # ← 关键：启动后不显示 Dock 图标（纯菜单栏）
    },
)
