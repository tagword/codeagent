"""Vision preset resolution for vision_analyze tool."""

from __future__ import annotations

import os
from typing import Any, Optional

from codeagent.core import env as ca_env


def list_vision_presets() -> list[dict[str, Any]]:
    from seed.core.llm_presets import load_presets

    return [p for p in load_presets() if preset_supports_vision(p)]


def preset_supports_vision(preset: dict[str, Any] | None) -> bool:
    if not isinstance(preset, dict):
        return False
    if preset.get("supports_vision") is True:
        return True
    return False


def preset_supports_vision_id(preset_id: str) -> bool:
    from seed.core.llm_presets import load_presets

    pid = (preset_id or "").strip()
    for p in load_presets():
        if str(p.get("id") or "").strip() == pid:
            return preset_supports_vision(p)
    return False


def resolve_preset_id(preset_id: Optional[str]) -> Optional[dict[str, Any]]:
    from seed.core.llm_presets import load_presets, resolve_preset

    pid = (preset_id or "").strip()
    if pid:
        for p in load_presets():
            if str(p.get("id") or "").strip() == pid:
                return p
        return None
    return resolve_preset(None)


def get_vision_executor(vision_llm_id: Optional[str] = None):
    from seed.core.llm_exec import get_llm_executor
    from seed.core.llm_presets import llm_executor_from_resolved

    pid = (vision_llm_id or "").strip()
    if not pid:
        pid = ca_env.pick_default("", "CODEAGENT_VISION_PRESET_ID").strip()
    preset = resolve_preset_id(pid) if pid else None
    if preset and preset_supports_vision(preset):
        return llm_executor_from_resolved(preset)
    if pid:
        raise ValueError(f"vision preset not found or not supports_vision: {pid}")
    raise ValueError("vision_llm_id required (no CODEAGENT_VISION_PRESET_ID fallback)")


def resolve_main_llm(llm_id: Optional[str] = None):
    from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset

    pid = (llm_id or "").strip()
    if pid:
        from seed.core.llm_presets import load_presets

        for p in load_presets():
            if str(p.get("id") or "").strip() == pid:
                preset = p
                break
        else:
            preset = resolve_preset(None)
    else:
        preset = resolve_preset(None)

    cfg = dict(preset)

    # 会话级 max_tokens 覆盖（CODEAGENT_CHAT_MAX_TOKENS / SEED_LLM_MAX_TOKENS）
    from codeagent.core import env as ca_env
    from seed.core import env_access as _ea

    mt_override = _ea.pick_nonempty(ca_env.CHAT_MAX_TOKENS)
    if not mt_override:
        mt_override = _ea.pick_nonempty(*_ea.LLM_MAX_TOKENS)
    if mt_override:
        try:
            cfg["max_tokens"] = int(mt_override)
        except (ValueError, TypeError):
            pass

    return llm_executor_from_resolved(cfg)
