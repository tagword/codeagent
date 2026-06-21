#!/usr/bin/env python3
"""
Stage external CLI tools for the macOS .app bundle.

Output layout (under build/bundle-tools/):
  bin/          git, node, npm, eslint, ast-grep, ruff, …
  node/         Node.js runtime
  npm-global/   eslint (global npm prefix)
  libexec/      git-core helpers
  share/        git templates (minimal)

Run automatically from build_mac_dmg.sh before PyInstaller.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "build" / "bundle-tools"
CACHE = ROOT / "build" / "cache"
BIN = OUT / "bin"
LIBEXEC = OUT / "libexec"
SHARE = OUT / "share"

AST_GREP_VERSION = os.environ.get("CODEAGENT_AST_GREP_VERSION", "0.40.3")
NODE_VERSION = os.environ.get("CODEAGENT_NODE_VERSION", "20.18.2")


def _machine() -> str:
    forced = os.environ.get("CODEAGENT_BUNDLE_ARCH", "").strip().lower()
    if forced in ("arm64", "aarch64"):
        return "aarch64-apple-darwin"
    if forced in ("x86_64", "amd64"):
        return "x86_64-apple-darwin"
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "aarch64-apple-darwin"
    if m in ("x86_64", "amd64"):
        return "x86_64-apple-darwin"
    raise SystemExit(f"Unsupported macOS arch: {platform.machine()}")


def _chmod_exec(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_exec(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    _chmod_exec(dest)
    print(f"  ✓ {dest.name}  ← {src}")


def _venv_bin(name: str) -> Path | None:
    venv = os.environ.get("VIRTUAL_ENV", "").strip()
    if venv:
        p = Path(venv) / "bin" / name
        if p.is_file():
            return p
    for candidate in (ROOT / ".build-venv" / "bin", ROOT / ".venv" / "bin"):
        p = candidate / name
        if p.is_file():
            return p
    which = shutil.which(name)
    return Path(which) if which else None


def _mach_minos(path: Path) -> str | None:
    try:
        out = subprocess.check_output(["otool", "-l", str(path)], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return None
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if "LC_BUILD_VERSION" not in line:
            continue
        for j in range(i + 1, min(i + 6, len(lines))):
            parts = lines[j].split()
            if len(parts) >= 2 and parts[0] == "minos":
                return parts[1]
    return None


def _minos_gt(version: str, target: str) -> bool:
    def _parts(v: str) -> list[int]:
        return [int(x) for x in v.split(".") if x.isdigit()]

    a, b = _parts(version), _parts(target)
    n = max(len(a), len(b))
    a.extend([0] * (n - len(a)))
    b.extend([0] * (n - len(b)))
    return a > b


def _bundle_git() -> None:
    print("==> git")
    candidates = [
        Path("/usr/bin/git"),
        Path("/Library/Developer/CommandLineTools/usr/bin/git"),
        Path("/opt/homebrew/bin/git"),
        Path("/usr/local/bin/git"),
    ]
    git_src = next((p for p in candidates if p.is_file()), None)
    if git_src is None:
        raise SystemExit("git not found — install Xcode Command Line Tools")

    minos = _mach_minos(git_src)
    bundle_local = minos is None or not _minos_gt(minos, "12.0")
    real_bin = BIN / "gitcmd"

    if bundle_local:
        _copy_exec(git_src, real_bin)
        clt_root = Path("/Library/Developer/CommandLineTools/usr")
        core_src = clt_root / "libexec" / "git-core"
        if core_src.is_dir() and git_src.as_posix().startswith("/Library/Developer/CommandLineTools"):
            core_dest = LIBEXEC / "git-core"
            if core_dest.exists():
                shutil.rmtree(core_dest)
            shutil.copytree(core_src, core_dest)
            print(f"  ✓ git-core  ← {core_src}")
        tmpl_src = clt_root / "share" / "git-core" / "templates"
        if tmpl_src.is_dir() and git_src.as_posix().startswith("/Library/Developer/CommandLineTools"):
            tmpl_dest = SHARE / "git-core" / "templates"
            if tmpl_dest.exists():
                shutil.rmtree(tmpl_dest)
            shutil.copytree(tmpl_src, tmpl_dest)
            print(f"  ✓ git templates  ← {tmpl_src}")
    else:
        print(f"  ⚠ skip bundled git binary (requires macOS {minos}; Monterey 12.x uses system git)")

    wrapper = BIN / "git"
    wrapper.write_text(
        "#!/bin/bash\n"
        'ROOT="$(cd "$(dirname "$0")/.." && pwd)"\n'
        'if [ -x "$ROOT/bin/gitcmd" ]; then\n'
        '  export GIT_EXEC_PATH="$ROOT/libexec/git-core"\n'
        '  export GIT_TEMPLATE_DIR="$ROOT/share/git-core/templates"\n'
        '  exec "$ROOT/bin/gitcmd" "$@"\n'
        "fi\n"
        'for g in /usr/bin/git /Library/Developer/CommandLineTools/usr/bin/git '
        '/usr/local/bin/git /opt/homebrew/bin/git; do\n'
        '  if [ -x "$g" ]; then exec "$g" "$@"; fi\n'
        "done\n"
        'echo "git not found" >&2\n'
        "exit 127\n",
        encoding="utf-8",
    )
    _chmod_exec(wrapper)
    print("  ✓ git wrapper")


def _write_python_shim() -> None:
    """``python -m pytest`` etc. via the frozen CodeAgent binary (see package_launcher)."""
    shim = BIN / "python"
    shim.write_text(
        "#!/bin/bash\n"
        '# From Contents/Resources/tools/bin → Contents/MacOS/CodeAgent\n'
        'RES="$(cd "$(dirname "$0")/../.." && pwd)"\n'
        'exec "$RES/MacOS/CodeAgent" -m "$@"\n',
        encoding="utf-8",
    )
    _chmod_exec(shim)
    print("  ✓ python shim (→ CodeAgent -m …)")


def _valid_zip(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def _download_ast_grep() -> None:
    print("==> ast-grep")
    dest = BIN / "ast-grep"
    if dest.is_file():
        print(f"  ✓ ast-grep already staged ({dest})")
        return

    def _use_local_fallback() -> bool:
        for fallback in ("ast-grep", "sg"):
            src = _venv_bin(fallback) or (Path(p) if (p := shutil.which(fallback)) else None)
            if src and src.is_file():
                _copy_exec(src, dest)
                print(f"  ✓ ast-grep  ← {src} (local fallback)")
                return True
        return False

    arch = _machine()
    asset = f"app-{arch}.zip"
    url = f"https://github.com/ast-grep/ast-grep/releases/download/{AST_GREP_VERSION}/{asset}"
    CACHE.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE / asset

    if not _valid_zip(zip_path):
        if zip_path.is_file():
            print(f"  ⚠ stale/incomplete cache, re-downloading {asset}")
            zip_path.unlink()
        print(f"  ↓ {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CodeAgent-bundle/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(zip_path, "wb") as out:
                shutil.copyfileobj(resp, out)
        except Exception as exc:
            print(f"  ⚠ download failed: {exc}")
            if _use_local_fallback():
                return
            raise SystemExit(
                "ast-grep download failed and no local ast-grep/sg on PATH. "
                "Install via `brew install ast-grep` or retry with network."
            ) from exc

    if not _valid_zip(zip_path):
        print(f"  ⚠ downloaded {asset} is not a valid zip")
        zip_path.unlink(missing_ok=True)
        if _use_local_fallback():
            return
        raise SystemExit(f"ast-grep download corrupt: {asset}")

    with tempfile.TemporaryDirectory(prefix="codeagent-sg-") as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(Path(tmp) / "extract")
        extracted = list((Path(tmp) / "extract").rglob("sg"))
        if not extracted:
            extracted = list((Path(tmp) / "extract").rglob("ast-grep"))
        if not extracted:
            raise SystemExit(f"ast-grep binary not found inside {asset}")
        _copy_exec(extracted[0], dest)

    sg_link = BIN / "sg"
    if not sg_link.exists():
        sg_link.symlink_to("ast-grep")
    print("  ✓ sg → ast-grep")


def _bundle_from_venv(name: str) -> None:
    src = _venv_bin(name)
    if src is None:
        print(f"  ⚠ {name} not found in venv — skip")
        return
    _copy_exec(src, BIN / name)


def _node_platform() -> str:
    return "darwin-arm64" if _machine() == "aarch64-apple-darwin" else "darwin-x64"


def _bundle_node() -> None:
    """Bundle Node.js + npm + eslint for WeChat mini program (JS/TS) game dev."""
    print("==> node / npm / eslint")
    node_home = OUT / "node"
    npm_prefix = OUT / "npm-global"
    node_bin = node_home / "bin" / "node"

    if not node_bin.is_file():
        plat = _node_platform()
        tarball = f"node-v{NODE_VERSION}-{plat}.tar.gz"
        url = f"https://nodejs.org/dist/v{NODE_VERSION}/{tarball}"
        CACHE.mkdir(parents=True, exist_ok=True)
        tar_path = CACHE / tarball

        if not tar_path.is_file():
            print(f"  ↓ {url}")
            try:
                urllib.request.urlretrieve(url, tar_path)
            except Exception as exc:
                print(f"  ⚠ download failed: {exc}")
                for name in ("node", "npm"):
                    src = Path(p) if (p := shutil.which(name)) else None
                    if src and src.is_file():
                        _copy_exec(src, BIN / name)
                if not (BIN / "node").is_file():
                    raise SystemExit(
                        "node download failed and no local node on PATH. "
                        "Install via `brew install node` or retry with network."
                    )
                print("  ✓ node/npm ← system (fallback)")
                return

        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(OUT, filter="data")
        extracted = OUT / f"node-v{NODE_VERSION}-{plat}"
        if extracted.is_dir():
            if node_home.exists():
                shutil.rmtree(node_home)
            extracted.rename(node_home)
        print(f"  ✓ node {NODE_VERSION}  ← {tarball}")

    for name in ("node", "npm", "npx"):
        src = node_home / "bin" / name
        if src.is_file():
            dest = BIN / name
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            dest.symlink_to(f"../node/bin/{name}")
            print(f"  ✓ {name}")

    npm_prefix.mkdir(parents=True, exist_ok=True)
    eslint_bin = npm_prefix / "bin" / "eslint"
    if not eslint_bin.is_file():
        env = os.environ.copy()
        env["npm_config_prefix"] = str(npm_prefix)
        try:
            subprocess.run(
                [str(node_home / "bin" / "npm"), "install", "-g", "eslint@9"],
                check=True,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            print("  ✓ eslint (npm global)")
        except Exception as exc:
            print(f"  ⚠ eslint install skipped: {exc}")
            src = Path(p) if (p := shutil.which("eslint")) else None
            if src and src.is_file():
                _copy_exec(src, BIN / "eslint")
                print(f"  ✓ eslint  ← {src} (fallback)")

    if eslint_bin.is_file():
        dest = BIN / "eslint"
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(f"../npm-global/bin/eslint")
        print("  ✓ eslint")


def _bundle_python_tools() -> None:
    print("==> Python CLI tools (from build venv)")
    _write_python_shim()
    _bundle_from_venv("ruff")
    # pytest / bandit / pip-audit run via ``python -m …`` using the shim above


def _write_manifest() -> None:
    manifest = OUT / "TOOLS.txt"
    lines = ["CodeAgent bundled dev tools\n"]
    for path in sorted(BIN.iterdir()):
        if path.is_file() or path.is_symlink():
            if path.is_symlink():
                lines.append(f"  bin/{path.name} -> {os.readlink(path)}")
            else:
                lines.append(f"  bin/{path.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("prepare_bundle_tools.py is macOS-only")

    print(f"Staging tools → {OUT}")
    if OUT.exists():
        shutil.rmtree(OUT)
    BIN.mkdir(parents=True)

    _bundle_git()
    _download_ast_grep()
    _bundle_node()
    _bundle_python_tools()
    _write_manifest()

    try:
        ver = subprocess.check_output([str(BIN / "git"), "--version"], text=True).strip()
        print(f"  git: {ver}")
    except Exception as exc:
        print(f"  ⚠ git smoke test failed: {exc}")

    try:
        ver = subprocess.check_output([str(BIN / "ast-grep"), "--version"], text=True).strip()
        print(f"  ast-grep: {ver}")
    except Exception as exc:
        print(f"  ⚠ ast-grep smoke test failed: {exc}")

    try:
        ver = subprocess.check_output([str(BIN / "node"), "--version"], text=True).strip()
        print(f"  node: {ver}")
    except Exception as exc:
        print(f"  ⚠ node smoke test failed: {exc}")

    try:
        ver = subprocess.check_output([str(BIN / "eslint"), "--version"], text=True).strip()
        print(f"  eslint: {ver}")
    except Exception as exc:
        print(f"  ⚠ eslint smoke test failed: {exc}")

    print("✅ bundle-tools ready")


if __name__ == "__main__":
    main()
