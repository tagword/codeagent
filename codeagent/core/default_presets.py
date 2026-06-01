"""Per-use-type default preset IDs.

Extends seed's `get_default_preset_id()` (which is a single chat-only default)
with a multi-slot default map: ``{chat: 'preset-abc', vision: 'preset-xyz', ...}``.

Storage:
- Primary: ``<config_dir>/codeagent.default_preset_ids.json`` (a JSON object)
- Fallback: the legacy single-id file from seed (which is
  ``seed.models.default.txt`` — that's the file that actually holds the
  chat default in the current install), assigned to the ``chat`` slot.

Slots: ``chat``, ``vision``, ``image_gen``, ``audio``, ``music``, ``video_gen``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# Ordered list of supported slots. "chat" must come first for legacy compat.
SLOTS: tuple[str, ...] = (
    "chat",
    "vision",
    "image_gen",
    "audio",
    "music",
    "video_gen",
)

# New canonical filename (sits next to the legacy single-id file)
DEFAULT_PRESET_IDS_FILENAME = "codeagent.default_preset_ids.json"


def _config_dir() -> Path:
    """Resolve the same config dir seed.core.llm_presets uses."""
    try:
        from seed.core.llm_presets import _config_dir as _seed_config_dir  # type: ignore
        return _seed_config_dir()
    except Exception:
        # Fallback (shouldn't normally trigger): SEED_PROJECT_ROOT/config
        import os
        root = os.environ.get("SEED_PROJECT_ROOT", "").strip() or "."
        return Path(root) / "config"


def _new_path() -> Path:
    return _config_dir() / DEFAULT_PRESET_IDS_FILENAME


def _legacy_path() -> Path | None:
    """Path of the legacy single-id file from seed, if any."""
    try:
        from seed.core.llm_presets import _default_id_read_path  # type: ignore
        p = _default_id_read_path()
        return p if p is not None else None
    except Exception:
        return None


def _read_legacy_single_id() -> str:
    p = _legacy_path()
    if p is None or not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def get_default_preset_ids() -> Dict[str, str]:
    """Return a mapping ``{slot: preset_id}`` for every slot that has a default.

    Reads the new JSON map first; falls back to the legacy single-id file
    (assigned to ``chat``) if the new file doesn't exist yet.
    """
    p = _new_path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
        except (json.JSONDecodeError, OSError):
            data = {}
        if isinstance(data, dict):
            out: Dict[str, str] = {}
            for slot in SLOTS:
                v = data.get(slot)
                if isinstance(v, str) and v.strip():
                    out[slot] = v.strip()
            return out
    # Legacy fallback: single id assigned to "chat"
    legacy = _read_legacy_single_id()
    if legacy:
        return {"chat": legacy}
    return {}


def set_default_preset_id_for_slot(slot: str, preset_id: str) -> None:
    """Set/clear the default for a single slot. Empty string clears."""
    if slot not in SLOTS:
        raise ValueError(f"unknown slot: {slot!r}")
    cur = get_default_preset_ids()
    pid = (preset_id or "").strip()
    if pid:
        cur[slot] = pid
    else:
        cur.pop(slot, None)
    _write_default_preset_ids(cur)


def set_default_preset_ids(mapping: Dict[str, str]) -> None:
    """Bulk-replace the entire default map (ignoring unknown slots)."""
    out: Dict[str, str] = {}
    for slot in SLOTS:
        if slot in mapping:
            v = mapping[slot]
            if isinstance(v, str) and v.strip():
                out[slot] = v.strip()
    _write_default_preset_ids(out)


def _write_default_preset_ids(mapping: Dict[str, str]) -> None:
    p = _new_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        logger.error("Failed to save default preset ids: %s", e)


# ---------------------------------------------------------------------------
# Backward-compat shim — keep `get_default_preset_id` and `set_default_preset_id`
# behaving as before for any in-process callers that still import them.
# ---------------------------------------------------------------------------

def get_default_preset_id() -> str:
    """Legacy single-id shim → returns the 'chat' default (or '' if none)."""
    return get_default_preset_ids().get("chat", "")


def set_default_preset_id(preset_id: str) -> None:
    """Legacy single-id shim → sets the 'chat' default."""
    set_default_preset_id_for_slot("chat", preset_id)
