"""MiniMax system TTS voices and models (curated from platform docs)."""

from __future__ import annotations

import os
from typing import Any

from seed_model_providers import list_models_for_provider

# https://platform.minimaxi.com/docs/faq/system-voice-id
TTS_SYSTEM_VOICES: list[dict[str, str]] = [
    {"id": "male-qn-qingse", "name": "青涩青年", "lang": "中文"},
    {"id": "male-qn-jingying", "name": "精英青年", "lang": "中文"},
    {"id": "male-qn-badao", "name": "霸道青年", "lang": "中文"},
    {"id": "male-qn-daxuesheng", "name": "青年大学生", "lang": "中文"},
    {"id": "female-shaonv", "name": "少女", "lang": "中文"},
    {"id": "female-yujie", "name": "御姐", "lang": "中文"},
    {"id": "female-chengshu", "name": "成熟女性", "lang": "中文"},
    {"id": "female-tianmei", "name": "甜美女性", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Lyrical_Voice", "name": "抒情男声", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Gentleman", "name": "温润男声", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Sweet_Lady", "name": "甜美女声", "lang": "中文"},
    {"id": "Chinese (Mandarin)_News_Anchor", "name": "新闻女声", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Male_Announcer", "name": "播报男声", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Radio_Host", "name": "电台男主播", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Reliable_Executive", "name": "沉稳高管", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Warm_Bestie", "name": "温暖闺蜜", "lang": "中文"},
    {"id": "Chinese (Mandarin)_HK_Flight_Attendant", "name": "港普空姐", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Humorous_Elder", "name": "搞笑大爷", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Crisp_Girl", "name": "清脆少女", "lang": "中文"},
    {"id": "Chinese (Mandarin)_Soft_Girl", "name": "柔和少女", "lang": "中文"},
    {"id": "Cantonese_ProfessionalHost（F)", "name": "粤语女主持", "lang": "粤语"},
    {"id": "Cantonese_GentleLady", "name": "粤语温柔女声", "lang": "粤语"},
    {"id": "Cantonese_ProfessionalHost（M)", "name": "粤语男主持", "lang": "粤语"},
    {"id": "English_Graceful_Lady", "name": "Graceful Lady", "lang": "英文"},
    {"id": "English_Trustworthy_Man", "name": "Trustworthy Man", "lang": "英文"},
    {"id": "English_Diligent_Man", "name": "Diligent Man", "lang": "英文"},
    {"id": "English_Gentle-voiced_man", "name": "Gentle-voiced man", "lang": "英文"},
    {"id": "English_Whispering_girl", "name": "Whispering girl", "lang": "英文"},
    {"id": "Japanese_GentleButler", "name": "Gentle Butler", "lang": "日文"},
    {"id": "Japanese_KindLady", "name": "Kind Lady", "lang": "日文"},
    {"id": "Korean_SweetGirl", "name": "Sweet Girl", "lang": "韩文"},
]

DEFAULT_TTS_VOICE_ID = "male-qn-qingse"
DEFAULT_TTS_MODEL = "speech-2.8-turbo"


def _speech_models_from_catalog() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in list_models_for_provider("minimax", "speech"):
        mid = str(m.get("id") or "").strip()
        if not mid:
            continue
        label = str(m.get("label") or mid).strip() or mid
        out.append({"id": mid, "name": label})
    return out


def _allowed_tts_models() -> set[str]:
    return {m["id"] for m in _speech_models_from_catalog()}


def default_tts_voice_id() -> str:
    v = os.environ.get("CODEAGENT_TTS_VOICE_ID", DEFAULT_TTS_VOICE_ID).strip()
    return v or DEFAULT_TTS_VOICE_ID


def default_tts_model() -> str:
    m = os.environ.get("CODEAGENT_TTS_MODEL", DEFAULT_TTS_MODEL).strip()
    return m or DEFAULT_TTS_MODEL


def normalize_tts_voice_id(voice_id: str | None) -> str:
    v = (voice_id or "").strip()
    if not v:
        return default_tts_voice_id()
    if len(v) > 128:
        return default_tts_voice_id()
    return v


def normalize_tts_model(model: str | None) -> str:
    m = (model or "").strip()
    allowed = _allowed_tts_models()
    if m in allowed:
        return m
    if not m:
        return default_tts_model()
    env_default = default_tts_model()
    return env_default if env_default in allowed else DEFAULT_TTS_MODEL


def tts_options_payload(*, configured: bool) -> dict[str, Any]:
    models = _speech_models_from_catalog()
    return {
        "configured": configured,
        "default_voice_id": default_tts_voice_id(),
        "default_model": default_tts_model(),
        "voices": TTS_SYSTEM_VOICES,
        "models": models,
        "docs_url": "https://platform.minimaxi.com/docs/faq/system-voice-id",
    }
