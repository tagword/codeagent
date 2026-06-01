"""Video generation preset resolution for video_generate tool."""

from __future__ import annotations

from typing import Any, Optional

from codeagent.core import env as ca_env


def list_video_gen_presets() -> list[dict[str, Any]]:
    from seed.core.llm_presets import load_presets

    return [p for p in load_presets() if preset_supports_video_gen(p)]


def preset_supports_video_gen(preset: dict[str, Any] | None) -> bool:
    if not isinstance(preset, dict):
        return False
    return preset.get("supports_video_gen") is True


def preset_supports_video_gen_id(preset_id: str) -> bool:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            return preset_supports_video_gen(p)
    return False


def resolve_video_gen_preset(preset_id: Optional[str] = None) -> dict[str, Any]:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    if not pid:
        pid = ca_env.pick_default("", "CODEAGENT_VIDEO_GEN_PRESET_ID").strip()
    if not pid:
        presets = list_video_gen_presets()
        if len(presets) == 1:
            return dict(presets[0])
        raise ValueError(
            "video preset required: set CODEAGENT_VIDEO_GEN_PRESET_ID or Web UI video_gen_llm_id"
        )
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            if preset_supports_video_gen(p):
                return dict(p)
            raise ValueError(f"preset {pid} does not support video generation")
    raise ValueError(f"video preset not found: {pid}")
