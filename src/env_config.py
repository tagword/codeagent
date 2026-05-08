"""Optional repo-local env file: config/codeagent.env (does not override existing os.environ)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.config_plane_pkg import project_root

ENV_FILENAME = "codeagent.env"


def _parse_line(line: str) -> Optional[tuple[str, str]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = key.strip()
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        val = val[1:-1]
    if not key:
        return None
    return key, val


def apply_codeagent_env_from_config(base: Optional[Path] = None) -> None:
    """
    Load KEY=VALUE lines from <project>/config/codeagent.env.
    Skips any key already present in os.environ so the shell/export wins.
    """
    root = project_root() if base is None else base.resolve()
    path = root / "config" / ENV_FILENAME
    if not path.is_file():
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        pair = _parse_line(line)
        if not pair:
            continue
        k, v = pair
        if k not in os.environ:
            os.environ[k] = v
