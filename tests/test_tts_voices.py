"""codeagent.core.tts_voices 单元测试。

覆盖 normalize_tts_voice_id / normalize_tts_model 的边界。
依赖外部 catalog 的函数用 monkeypatch 隔离。
"""
import pytest

from codeagent.core import tts_voices as tv


# ---------- normalize_tts_voice_id ----------
def test_normalize_voice_id_normal(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_VOICE_ID", "")
    assert tv.normalize_tts_voice_id("female-shaonv") == "female-shaonv"


def test_normalize_voice_id_strips(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_VOICE_ID", "")
    assert tv.normalize_tts_voice_id("  male-qn-qingse  ") == "male-qn-qingse"


def test_normalize_voice_id_empty_uses_default(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_VOICE_ID", "")
    assert tv.normalize_tts_voice_id("") == tv.DEFAULT_TTS_VOICE_ID
    assert tv.normalize_tts_voice_id(None) == tv.DEFAULT_TTS_VOICE_ID


def test_normalize_voice_id_empty_uses_env_default(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_VOICE_ID", "custom-voice")
    assert tv.normalize_tts_voice_id("") == "custom-voice"


def test_normalize_voice_id_too_long_uses_default(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_VOICE_ID", "")
    long_id = "x" * 200
    assert tv.normalize_tts_voice_id(long_id) == tv.DEFAULT_TTS_VOICE_ID


def test_normalize_voice_id_128_chars_ok(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_VOICE_ID", "")
    v = "v" * 128
    assert tv.normalize_tts_voice_id(v) == v


# ---------- normalize_tts_model ----------
def test_normalize_model_in_allowed(monkeypatch):
    monkeypatch.setattr(tv, "_allowed_tts_models", lambda: {"speech-2.8-turbo", "speech-2.5"})
    monkeypatch.setattr(tv, "default_tts_model", lambda: "speech-2.8-turbo")
    assert tv.normalize_tts_model("speech-2.5") == "speech-2.5"


def test_normalize_model_empty_uses_env_default(monkeypatch):
    monkeypatch.setattr(tv, "_allowed_tts_models", lambda: {"speech-2.8-turbo"})
    monkeypatch.setattr(tv, "default_tts_model", lambda: "speech-2.8-turbo")
    assert tv.normalize_tts_model("") == "speech-2.8-turbo"
    assert tv.normalize_tts_model(None) == "speech-2.8-turbo"


def test_normalize_model_unknown_falls_to_env_default(monkeypatch):
    monkeypatch.setattr(tv, "_allowed_tts_models", lambda: {"speech-2.8-turbo"})
    monkeypatch.setattr(tv, "default_tts_model", lambda: "speech-2.8-turbo")
    assert tv.normalize_tts_model("bad-model") == "speech-2.8-turbo"


def test_normalize_model_env_default_not_allowed_uses_hardcoded(monkeypatch):
    # 非空未知 model：env default 不在 catalog → 回退 DEFAULT_TTS_MODEL
    monkeypatch.setattr(tv, "_allowed_tts_models", lambda: {"speech-2.5"})
    monkeypatch.setattr(tv, "default_tts_model", lambda: "not-in-catalog")
    assert tv.normalize_tts_model("some-model") == tv.DEFAULT_TTS_MODEL


def test_normalize_model_empty_always_uses_env_default(monkeypatch):
    # 空 model 信任 env 配置（即使不在 catalog），不回退硬编码
    monkeypatch.setattr(tv, "_allowed_tts_models", lambda: {"speech-2.5"})
    monkeypatch.setattr(tv, "default_tts_model", lambda: "custom-env-model")
    assert tv.normalize_tts_model("") == "custom-env-model"


def test_normalize_model_empty_catalog_returns_default(monkeypatch):
    # catalog 空 → 任何非空 model 都不在 allowed；空 model 用 env default
    monkeypatch.setattr(tv, "_allowed_tts_models", lambda: set())
    monkeypatch.setattr(tv, "default_tts_model", lambda: tv.DEFAULT_TTS_MODEL)
    assert tv.normalize_tts_model("") == tv.DEFAULT_TTS_MODEL


# ---------- tts_options_payload ----------
def test_tts_options_payload_structure(monkeypatch):
    monkeypatch.setattr(tv, "_speech_models_from_catalog", lambda: [{"id": "m1", "name": "Model1"}])
    monkeypatch.setattr(tv, "default_tts_voice_id", lambda: tv.DEFAULT_TTS_VOICE_ID)
    monkeypatch.setattr(tv, "default_tts_model", lambda: "m1")
    p = tv.tts_options_payload(configured=True)
    assert p["configured"] is True
    assert p["default_voice_id"] == tv.DEFAULT_TTS_VOICE_ID
    assert p["models"] == [{"id": "m1", "name": "Model1"}]
    assert len(p["voices"]) > 0
    assert "docs_url" in p
