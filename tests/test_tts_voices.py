"""Tests for TTS voice catalog."""

from codeagent.core.tts_voices import (
    normalize_tts_model,
    normalize_tts_voice_id,
    tts_options_payload,
)


def test_normalize_tts_voice_id_defaults() -> None:
    assert normalize_tts_voice_id("") == "male-qn-qingse"
    assert normalize_tts_voice_id("female-shaonv") == "female-shaonv"


def test_normalize_tts_model() -> None:
    assert normalize_tts_model("speech-2.8-hd") == "speech-2.8-hd"
    assert normalize_tts_model("invalid") != "invalid"


def test_tts_options_payload() -> None:
    p = tts_options_payload(configured=True)
    assert p["configured"] is True
    assert p["voices"]
    assert p["models"]
    assert p["docs_url"]
