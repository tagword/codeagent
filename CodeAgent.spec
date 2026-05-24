# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F405

# ── 数据文件 ──────────────────────────────────────────────
_datas = []
_binaries = []

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

# Bundled dev tools (git, ast-grep, ruff, pytest, …) — staged by prepare_bundle_tools.py
_tools_root = ROOT / "build" / "bundle-tools"
if _tools_root.is_dir():
    _tools_bin = _tools_root / "bin"
    if _tools_bin.is_dir():
        for _exe in sorted(_tools_bin.iterdir()):
            if _exe.is_file() and not _exe.is_symlink():
                _binaries.append((str(_exe), "tools/bin"))
            elif _exe.is_symlink():
                # Resolve symlink target for PyInstaller (e.g. sg → ast-grep)
                _target = _exe.resolve()
                if _target.is_file():
                    _binaries.append((str(_target), "tools/bin"))
    for _subdir in ("libexec", "share", "node", "npm-global"):
        _src = _tools_root / _subdir
        if _src.is_dir():
            for _p in sorted(_src.rglob("*")):
                if _p.is_file():
                    _rel = _p.relative_to(_tools_root)
                    _datas.append((str(_p), str(Path("tools") / _rel.parent)))

a = Analysis(
    ['package_launcher.py'],
    pathex=[str(ROOT)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'pytest',
        'ruff',
        'bandit',
        'pip_audit',
        'jaraco.text',
        'jaraco.functools',
        'jaraco.context',
        'platformdirs',
        'seed',
        'seed_tools',
        'codeagent',
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
        'LSMinimumSystemVersion': '12.0',  # macOS Monterey 12.7.6+
    },
)
