# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F405

# ── 数据文件 ──────────────────────────────────────────────
_datas = []

# 托盘图标（放置于 Resources 根目录 = sys._MEIPASS）
for _name in ("tray_icon.png", "tray_icon@2x.png"):
    _p = ROOT / _name
    if _p.exists():
        _datas.append((str(_p), "."))

# WebUI 静态资源
_webui = ROOT / "codeagent" / "webui"
if _webui.is_dir():
    for p in sorted(_webui.rglob("*")):
        if p.is_file():
            _datas.append((str(p), "codeagent/webui"))

# 主 HTML 模板（app_factory.py 运行时通过 __file__ 相对路径加载）
_webui_html = ROOT / "codeagent" / "webui.html"
if _webui_html.exists():
    _datas.append((str(_webui_html), "codeagent"))

# 网站图标（server/icon.png — 同样通过 __file__ 相对路径定位）
_server_icon = ROOT / "codeagent" / "server" / "icon.png"
if _server_icon.exists():
    _datas.append((str(_server_icon), "codeagent/server"))

a = Analysis(
    ['package_launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest', 'distutils', 'setuptools', 'pip'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CodeAgent',
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
    icon=['codeagent.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CodeAgent',
)
app = BUNDLE(
    coll,
    name='CodeAgent.app',
    icon='codeagent.icns',
    bundle_identifier='com.codeagent.app',
    info_plist={
        'LSUIElement': True,  # 纯托盘，不显示 Dock 图标
    },
)
