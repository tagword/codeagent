# -*- mode: python ; coding: utf-8 -*-
# Windows-specific PyInstaller spec (no BUNDLE step — macOS only)
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)  # noqa: F405
MONO = ROOT.parent

# ── Data files ──────────────────────────────────────────────
_datas = []
_binaries = []
_hidden = [
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'pytest',
    'ruff',
    'bandit',
    'pip_audit',
    'jaraco',
    'jaraco.text',
    'jaraco.functools',
    'jaraco.context',
    'setuptools._vendor.jaraco.text',
    'setuptools._vendor.jaraco.functools',
    'setuptools._vendor.jaraco.context',
    'platformdirs',
]

# Monorepo Python packages (editable installs need explicit collect_all)
for _pkg in ('seed', 'seed_model_providers', 'seed_tools', 'codeagent'):
    _pd, _pb, _ph = collect_all(_pkg)
    _datas += _pd
    _binaries += _pb
    _hidden += _ph

# Bundled dev tools — staged by prepare_bundle_tools.py
_tools_root = MONO / "build" / "bundle-tools"
if _tools_root.is_dir():
    _tools_bin = _tools_root / "bin"
    if _tools_bin.is_dir():
        for _exe in sorted(_tools_bin.iterdir()):
            if _exe.is_file() and not _exe.is_symlink():
                _binaries.append((str(_exe), "tools/bin"))
            elif _exe.is_symlink():
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

# 托盘图标
for _name in ("tray_icon.png", "tray_icon@2x.png"):
    _p = MONO / "assets" / _name
    if _p.exists():
        _datas.append((str(_p), "."))

a = Analysis(
    ['package_launcher.py'],
    pathex=[str(MONO), str(MONO / "seed"), str(MONO / "seed-tools"), str(MONO / "seed-model-providers")],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest', 'distutils', 'pip'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CodeAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(MONO / 'assets' / 'codeagent.ico')],
)
