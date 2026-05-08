"""Web UI: plugin toggles and which config/*.md files feed the system prompt."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config_plane_pkg import CONFIG_FILENAMES, config_dir

logger = logging.getLogger(__name__)

PLUGINS_FILENAME = "codeagent.plugins.json"


def _defaults() -> Dict[str, Any]:
    return {
        "config_md_enabled": list(CONFIG_FILENAMES),
        "plugins": {},
    }


def _plugins_path(base: Optional[Path] = None) -> Path:
    cfg = config_dir() if base is None else base.resolve() / "config"
    return cfg / PLUGINS_FILENAME


def load_plugins(base: Optional[Path] = None) -> Dict[str, Any]:
    d = _defaults()
    path = _plugins_path(base)
    if not path.is_file():
        return d
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ignore bad %s: %s", path, e)
        return d
    if not isinstance(raw, dict):
        return d
    if isinstance(raw.get("config_md_enabled"), list):
        sel = [
            x
            for x in raw["config_md_enabled"]
            if isinstance(x, str) and x in CONFIG_FILENAMES
        ]
        if sel:
            d["config_md_enabled"] = sel
    pl = raw.get("plugins")
    if isinstance(pl, dict):
        d["plugins"] = pl
    return d


def save_plugins(data: Dict[str, Any], base: Optional[Path] = None) -> None:
    path = _plugins_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def get_system_prompt_filenames(base: Optional[Path] = None) -> List[str]:
    data = load_plugins(base) if base is not None else load_plugins()
    enabled = data.get("config_md_enabled") or list(CONFIG_FILENAMES)
    if not enabled:
        return list(CONFIG_FILENAMES)
    s = set(enabled)
    ordered = [f for f in CONFIG_FILENAMES if f in s]
    if not ordered:
        return list(CONFIG_FILENAMES)
    return ordered


def get_tool_exclude_prefixes() -> Tuple[str, ...]:
    return ()


def plugins_public_view() -> Dict[str, Any]:
    d = load_plugins()
    en = set(d.get("config_md_enabled") or CONFIG_FILENAMES)
    return {
        "config_filenames": list(CONFIG_FILENAMES),
        "config_md": [{"name": f, "enabled": f in en} for f in CONFIG_FILENAMES],
        "plugins": d.get("plugins", _defaults()["plugins"]),
    }


def save_plugins_from_ui(body: Dict[str, Any]) -> Dict[str, Any]:
    current = load_plugins()
    enabled = body.get("config_md_enabled")
    if enabled is not None:
        if not isinstance(enabled, list):
            raise ValueError("config_md_enabled must be a list of filenames")
        sel = [x for x in enabled if isinstance(x, str) and x in CONFIG_FILENAMES]
        if not sel:
            sel = list(CONFIG_FILENAMES)
        current["config_md_enabled"] = sel
    pl = body.get("plugins")
    if isinstance(pl, dict):
        current["plugins"] = pl
    save_plugins(current)