"""
LLM Presets Manager - Manage multiple LLM configurations.

Presets are stored in ``config/codeagent.models.json`` as a list of named
configurations. Each preset has::

    {
        "id": "my-deepseek",
        "name": "DeepSeek V3",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "sk-...",
        "auth_scheme": "Bearer",
        "max_tokens": 8192
    }

The default preset ID is stored in ``config/codeagent.models.default.txt``.
Resolution order for ``resolve_preset(None)``:

1. Preset whose ``id`` matches the stored default (if any).
2. Else ``CODEAGENT_LLM_BASEURL`` / related env vars (if Base URL is non-empty).
3. Else the **first** preset in ``codeagent.models.json`` that has both Base URL and model
   (so a single saved preset works without clicking「设为默认」).

On first access, legacy paths ``llm_presets.json`` / ``llm_default.txt`` are
renamed to the new filenames when the new files do not yet exist.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from seed.config_plane import project_root

logger = logging.getLogger(__name__)

PRESETS_FILENAME = "codeagent.models.json"
DEFAULT_ID_FILENAME = "codeagent.models.default.txt"

_LEGACY_PRESETS = "llm_presets.json"
_LEGACY_DEFAULT_ID = "llm_default.txt"


def _migrate_legacy_config_paths(cfg: Path) -> None:
    """Rename legacy preset files if new paths are missing."""
    try:
        cfg.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    new_p = cfg / PRESETS_FILENAME
    old_p = cfg / _LEGACY_PRESETS
    if not new_p.is_file() and old_p.is_file():
        try:
            old_p.replace(new_p)
        except OSError:
            try:
                new_p.write_bytes(old_p.read_bytes())
                old_p.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Could not migrate %s -> %s: %s", old_p, new_p, e)

    new_d = cfg / DEFAULT_ID_FILENAME
    old_d = cfg / _LEGACY_DEFAULT_ID
    if not new_d.is_file() and old_d.is_file():
        try:
            old_d.replace(new_d)
        except OSError:
            try:
                new_d.write_bytes(old_d.read_bytes())
                old_d.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Could not migrate %s -> %s: %s", old_d, new_d, e)


def _presets_path() -> Path:
    cfg = project_root() / "config"
    _migrate_legacy_config_paths(cfg)
    return cfg / PRESETS_FILENAME


def _default_id_path() -> Path:
    cfg = project_root() / "config"
    _migrate_legacy_config_paths(cfg)
    return cfg / DEFAULT_ID_FILENAME


# ---------------------------------------------------------------------------
# Load / save presets
# ---------------------------------------------------------------------------

def load_presets() -> List[Dict[str, Any]]:
    path = _presets_path()
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return [p for p in data if isinstance(p, dict) and p.get("id") != "__default__"]
        if isinstance(data, dict):
            presets = data.get("presets")
            if isinstance(presets, list):
                return [p for p in presets if isinstance(p, dict) and p.get("id") != "__default__"]
        return []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load LLM presets from %s: %s", path, e)
        return []


def save_presets(presets: List[Dict[str, Any]]) -> None:
    path = _presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for p in presets:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if not pid or pid == "__default__":
            continue
        if pid in seen:
            continue
        seen.add(pid)
        entry: Dict[str, Any] = {"id": pid}
        for k in ("name", "base_url", "model", "api_key", "auth_scheme"):
            val = p.get(k)
            if val is not None:
                entry[k] = str(val).strip() if isinstance(val, str) else val
        if p.get("max_tokens") is not None:
            try:
                entry["max_tokens"] = int(p["max_tokens"])
            except (ValueError, TypeError):
                pass
        clean.append(entry)
    try:
        path.write_text(
            json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        logger.error("Failed to save LLM presets: %s", e)


# ---------------------------------------------------------------------------
# Default preset
# ---------------------------------------------------------------------------

def get_default_preset_id() -> str:
    """Returns the stored default preset ID, or empty string if none."""
    path = _default_id_path()
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def set_default_preset_id(preset_id: str) -> None:
    """Persist the default preset ID (empty string clears it)."""
    path = _default_id_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text((preset_id or "").strip(), encoding="utf-8")
    except OSError as e:
        logger.error("Failed to save default LLM preset ID: %s", e)


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

def _preset_to_cfg(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "base_url": str(p.get("base_url") or "").rstrip("/"),
        "model": str(p.get("model") or ""),
        "api_key": str(p.get("api_key") or ""),
        "auth_scheme": str(p.get("auth_scheme") or "Bearer"),
        "max_tokens": int(p.get("max_tokens") or 8192),
    }


def resolve_preset(preset_id: Optional[str]) -> Dict[str, Any]:
    """
    Resolve a preset ID to an effective config dict.
    See module docstring for ``preset_id`` None / ``__default__`` / env / first-preset rules.
    """
    presets = load_presets()
    pid = (preset_id or "").strip()
    if not pid or pid == "__default__":
        pid = get_default_preset_id().strip()

    env_cfg = _env_config_dict()

    if pid:
        for p in presets:
            if str(p.get("id") or "").strip() == pid:
                return _preset_to_cfg(p)

    if env_cfg.get("base_url"):
        return env_cfg

    for p in presets:
        bu = str(p.get("base_url") or "").strip()
        mo = str(p.get("model") or "").strip()
        if bu and mo:
            return _preset_to_cfg(p)

    return env_cfg


def llm_executor_from_resolved(cfg: Dict[str, Any]):
    """Build the process-wide cached ``LLMAPIExecutor`` from ``resolve_preset`` output."""
    from seed.llm_exec import get_llm_executor

    bu = (cfg.get("base_url") or "").strip().rstrip("/")
    mod = (cfg.get("model") or "").strip()
    pk = (cfg.get("api_key") or "").strip()
    scheme = (cfg.get("auth_scheme") or "").strip()
    mt = cfg.get("max_tokens")
    mt_arg = int(mt) if mt is not None else None
    return get_llm_executor(
        baseURL=bu if bu else None,
        model=mod if mod else None,
        api_key=pk if pk else None,
        auth_scheme=scheme if scheme else None,
        max_tokens=mt_arg,
    )


def _env_config_dict() -> Dict[str, Any]:
    return {
        "base_url": (os.environ.get("CODEAGENT_LLM_BASEURL") or "").strip().rstrip("/"),
        "model": os.environ.get("CODEAGENT_LLM_MODEL", "Qwen/Qwen3.5-35B-A3B-GPTQ-Int4"),
        "api_key": os.environ.get("CODEAGENT_LLM_API_KEY", "").strip(),
        "auth_scheme": os.environ.get("CODEAGENT_LLM_AUTH_SCHEME", "Bearer").strip() or "Bearer",
        "max_tokens": int(os.environ.get("CODEAGENT_LLM_MAX_TOKENS", "8192")),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_preset(p: Dict[str, Any]) -> Optional[str]:
    pid = str(p.get("id") or "").strip()
    if not pid:
        return "预设 ID 不能为空"
    if pid == "__default__":
        return "ID '__default__' 为保留值"
    if not str(p.get("base_url") or "").strip():
        return "Base URL 不能为空"
    if not str(p.get("model") or "").strip():
        return "模型名称不能为空"
    return None
