"""
Configure PATH and tool env when CodeAgent runs from a PyInstaller .app bundle.

Bundled layout (sys._MEIPASS/tools/):
  bin/       git, node, npm, eslint, ast-grep, ruff, …
  node/      Node.js runtime (WeChat mini program JS/TS toolchain)
  libexec/   git-core
  share/     git templates
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path | None:
    if not is_frozen():
        return None
    root = Path(sys._MEIPASS) / "tools"
    return root if root.is_dir() else None


def bundled_bin_dir() -> Path | None:
    root = bundle_root()
    if root is None:
        return None
    bin_dir = root / "bin"
    return bin_dir if bin_dir.is_dir() else None


def setup_bundled_tools_env() -> Path | None:
    """
    Prepend bundled tool ``bin/`` to PATH and set git helper env vars.
    Safe to call multiple times; no-op when not frozen or tools missing.
    """
    root = bundle_root()
    bin_dir = bundled_bin_dir()
    if root is None or bin_dir is None:
        return None

    path = os.environ.get("PATH", "")
    prefix = str(bin_dir)
    if not path.startswith(prefix):
        os.environ["PATH"] = f"{prefix}{os.pathsep}{path}" if path else prefix

    git_core = root / "libexec" / "git-core"
    if git_core.is_dir():
        os.environ.setdefault("GIT_EXEC_PATH", str(git_core))

    git_tmpl = root / "share" / "git-core" / "templates"
    if git_tmpl.is_dir():
        os.environ.setdefault("GIT_TEMPLATE_DIR", str(git_tmpl))

    node_home = root / "node"
    if node_home.is_dir():
        os.environ.setdefault("NODE_HOME", str(node_home))

    os.environ["CODEAGENT_BUNDLED_TOOLS"] = str(root)
    return bin_dir
