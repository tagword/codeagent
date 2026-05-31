"""Music generation preset resolution for music_generate tool."""

from __future__ import annotations

from typing import Any, Optional

from codeagent.core import env as ca_env


def list_music_presets() -> list[dict[str, Any]]:
    from seed.core.llm_presets import load_presets

    return [p for p in load_presets() if preset_supports_music(p)]


def preset_supports_music(preset: dict[str, Any] | None) -> bool:
    if not isinstance(preset, dict):
        return False
    return preset.get("supports_music") is True


def preset_supports_music_id(preset_id: str) -> bool:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            return preset_supports_music(p)
    return False


def resolve_music_preset(preset_id: Optional[str] = None) -> dict[str, Any]:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    if not pid:
        pid = ca_env.pick_default("", "CODEAGENT_MUSIC_GEN_PRESET_ID").strip()
    if not pid:
        presets = list_music_presets()
        if len(presets) == 1:
            return dict(presets[0])
        raise ValueError(
            "music preset required: set CODEAGENT_MUSIC_GEN_PRESET_ID or Web UI music_llm_id"
        )
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            if preset_supports_music(p):
                return dict(p)
            raise ValueError(f"preset {pid} does not support music generation")
    raise ValueError(f"music preset not found: {pid}")
