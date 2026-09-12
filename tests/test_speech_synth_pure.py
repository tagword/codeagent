"""codeagent.core.speech_synth 纯辅助函数单元测试。

聚焦无 IO 的纯函数：
1. _base_resp_status_code：解析 status_code/status_msg
2. _host_from_preset_base_url：从 base_url 提取 host
3. _max_tts_chars：TTS 字符上限（含环境变量边界）
4. _humanize_tts_error：错误人性化（含 2056 Token Plan 特判）
"""

from codeagent.core.speech_synth import (
    _base_resp_status_code,
    _host_from_preset_base_url,
    _humanize_tts_error,
    _max_tts_chars,
)


# ---------- _base_resp_status_code ----------
def test_base_resp_none():
    assert _base_resp_status_code(None) == (0, "")
    assert _base_resp_status_code("not-dict") == (0, "")
    assert _base_resp_status_code(123) == (0, "")


def test_base_resp_normal():
    assert _base_resp_status_code({"status_code": 200, "status_msg": "ok"}) == (200, "ok")


def test_base_resp_missing_fields():
    assert _base_resp_status_code({}) == (0, "")
    assert _base_resp_status_code({"status_code": 200}) == (200, "")


def test_base_resp_non_numeric_code():
    assert _base_resp_status_code({"status_code": "abc"}) == (0, "")
    assert _base_resp_status_code({"status_code": None}) == (0, "")


def test_base_resp_strips_msg():
    assert _base_resp_status_code({"status_code": 1, "status_msg": "  padded  "}) == (1, "padded")


# ---------- _host_from_preset_base_url ----------
def test_host_strips_v1_suffix():
    assert _host_from_preset_base_url("https://api.minimaxi.com/v1") == "https://api.minimaxi.com"


def test_host_strips_v1_t2a_suffix():
    assert _host_from_preset_base_url("https://api.minimaxi.com/v1/t2a_v2") == "https://api.minimaxi.com"


def test_host_passthrough_other_path():
    assert _host_from_preset_base_url("http://example.com/base") == "http://example.com/base"


def test_host_empty_returns_default():
    assert _host_from_preset_base_url("") == "https://api.minimaxi.com"
    assert _host_from_preset_base_url(None) == "https://api.minimaxi.com"


def test_host_strips_trailing_slash():
    assert _host_from_preset_base_url("https://api.minimaxi.com/") == "https://api.minimaxi.com"


# ---------- _max_tts_chars ----------
def test_max_chars_default(monkeypatch):
    monkeypatch.delenv("CODEAGENT_TTS_MAX_CHARS", raising=False)
    assert _max_tts_chars() == 2000


def test_max_chars_custom(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_MAX_CHARS", "5000")
    assert _max_tts_chars() == 5000


def test_max_chars_clamped_upper(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_MAX_CHARS", "99999")
    assert _max_tts_chars() == 10000


def test_max_chars_clamped_lower(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_MAX_CHARS", "0")
    assert _max_tts_chars() == 1


def test_max_chars_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("CODEAGENT_TTS_MAX_CHARS", "not-a-number")
    assert _max_tts_chars() == 2000


# ---------- _humanize_tts_error ----------
def test_humanize_normal_error():
    r = _humanize_tts_error(1004, "some error")
    assert r == "some error"


def test_humanize_no_msg_uses_code():
    r = _humanize_tts_error(1004, "")
    assert "1004" in r


def test_humanize_no_code_no_msg():
    r = _humanize_tts_error(None, "")
    assert "MiniMax TTS failed" in r


def test_humanize_2056_token_plan_hint():
    r = _humanize_tts_error(2056, "Token Plan 0/0 exhausted")
    assert "sk-cp-" in r  # 含按量 key 提示


def test_humanize_2056_does_not_add_hint_if_not_quota():
    r = _humanize_tts_error(2056, "some other 2056 error")
    # 非 0/0 或 Token Plan 文案 → 不追加 hint
    assert "Token Plan Key" not in r
