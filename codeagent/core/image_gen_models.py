"""Image generation preset resolution for image_generate tool."""

from __future__ import annotations

from typing import Any, Optional

from codeagent.core import env as ca_env


def list_image_gen_presets() -> list[dict[str, Any]]:
    from seed.core.llm_presets import load_presets

    return [p for p in load_presets() if preset_supports_image_gen(p)]


def preset_supports_image_gen(preset: dict[str, Any] | None) -> bool:
    if not isinstance(preset, dict):
        return False
    return preset.get("supports_image_gen") is True


def preset_supports_image_gen_id(preset_id: str) -> bool:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            return preset_supports_image_gen(p)
    return False


def resolve_image_gen_preset(preset_id: Optional[str] = None) -> dict[str, Any]:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    if not pid:
        pid = ca_env.pick_default("", "CODEAGENT_IMAGE_GEN_PRESET_ID").strip()
    if not pid:
        presets = list_image_gen_presets()
        if len(presets) == 1:
            return dict(presets[0])
        raise ValueError(
            "image_gen preset required: set CODEAGENT_IMAGE_GEN_PRESET_ID or Web UI image_gen_llm_id"
        )
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            if preset_supports_image_gen(p):
                return dict(p)
            raise ValueError(f"preset {pid} does not support image generation")
    raise ValueError(f"image_gen preset not found: {pid}")
