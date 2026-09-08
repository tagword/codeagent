"""codeagent.server 工具摘要追加 + env 布尔解析单元测试。

覆盖 _reply_append_tool_summary（deepseek 特判/开关/空处理）与 _env_truthy。
"""
import codeagent.server as server
from codeagent.server import _env_truthy, _reply_append_tool_summary


def _clear(monkeypatch):
    for k in ("CODEAGENT_LLM_BASEURL", "CODEAGENT_REPLY_TOOL_SUMMARY",
              "CODEAGENT_REPLY_TOOL_SUMMARY_DEEPSEEK"):
        monkeypatch.delenv(k, raising=False)


# ---------- _env_truthy ----------
def test_env_truthy_true_values(monkeypatch):
    for v in ("1", "true", "True", "yes", "on", " 1 "):
        monkeypatch.setenv("X", v)
        assert _env_truthy("X") is True


def test_env_truthy_false_values(monkeypatch):
    for v in ("0", "false", "no", "off", "", "banana"):
        monkeypatch.setenv("X", v)
        assert _env_truthy("X") is False


def test_env_truthy_default(monkeypatch):
    monkeypatch.delenv("X", raising=False)
    assert _env_truthy("X") is False  # default "0"
    assert _env_truthy("X", default="1") is True


# ---------- _reply_append_tool_summary ----------
def test_empty_summary_returns_reply():
    assert _reply_append_tool_summary("hi", "") == "hi"
    assert _reply_append_tool_summary("hi", "   ") == "hi"


def test_empty_reply_returns_summary(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "1")
    assert _reply_append_tool_summary("", "summary") == "summary"


def test_append_summary_to_reply(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "1")
    out = _reply_append_tool_summary("answer", "tool summary")
    assert out == "answer\n\ntool summary"


def test_append_trimmed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "1")
    out = _reply_append_tool_summary("answer  ", "  summary  ")
    assert out == "answer\n\nsummary"


def test_global_summary_disabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "0")
    assert _reply_append_tool_summary("answer", "summary") == "answer"


def test_deepseek_disables_by_default(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_LLM_BASEURL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "1")
    # deepseek 且未显式开启 deepseek 特判 → 不追加
    assert _reply_append_tool_summary("answer", "summary") == "answer"


def test_deepseek_enabled_when_opt_in(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_LLM_BASEURL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "1")
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY_DEEPSEEK", "1")
    assert _reply_append_tool_summary("answer", "summary") == "answer\n\nsummary"


def test_non_deepseek_appends(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("CODEAGENT_LLM_BASEURL", "https://other.com/v1")
    monkeypatch.setenv("CODEAGENT_REPLY_TOOL_SUMMARY", "1")
    assert _reply_append_tool_summary("answer", "summary") == "answer\n\nsummary"
