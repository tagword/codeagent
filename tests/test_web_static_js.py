"""Syntax checks for the Web UI JavaScript bundle."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


STATIC_JS_DIR = Path(__file__).resolve().parents[1] / "codeagent" / "web" / "static"


def test_webui_javascript_bundle_parses(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for Web UI JavaScript syntax checks")

    # Mirrors codeagent.server.get_app_html(), which injects sorted static JS
    # files into one script block instead of serving each file independently.
    js_files = sorted(STATIC_JS_DIR.glob("*.js"))
    bundle = "\n\n".join(path.read_text(encoding="utf-8") for path in js_files)
    bundle_path = tmp_path / "webui-bundle.js"
    bundle_path.write_text(bundle, encoding="utf-8")

    result = subprocess.run(
        [node, "--check", str(bundle_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
