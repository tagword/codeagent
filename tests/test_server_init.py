"""codeagent.server（__init__）安全与纯逻辑单元测试。

覆盖 webhook 签名验证（安全关键）、监听接口判断、auto-continue 策略消息、
历史分块、运行中会话集合（线程安全）。
"""
import hashlib
import hmac
import os
import threading

import pytest

from codeagent.server import (
    _auto_continue_nudge,
    _listens_on_all_interfaces,
    _running_add,
    _running_contains,
    _running_discard,
    _running_list,
    _verify_webhook_signature,
    _webui_history_partition_user_blocks,
)


# ---------- _verify_webhook_signature ----------
def _sig(body, secret):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_valid_signature(monkeypatch):
    monkeypatch.setenv("CODEAGENT_WEBHOOK_SECRET", "secret-1")
    body = b'{"msg": "hi"}'
    assert _verify_webhook_signature(body, _sig(body, "secret-1")) is True


def test_webhook_wrong_signature(monkeypatch):
    monkeypatch.setenv("CODEAGENT_WEBHOOK_SECRET", "secret-1")
    body = b'hello'
    assert _verify_webhook_signature(body, _sig(body, "wrong-secret")) is False


def test_webhook_tampered_body(monkeypatch):
    monkeypatch.setenv("CODEAGENT_WEBHOOK_SECRET", "secret-1")
    body = b'hello'
    sig = _sig(body, "secret-1")
    assert _verify_webhook_signature(b'hello!', sig) is False


def test_webhook_no_secret_rejects(monkeypatch):
    monkeypatch.delenv("CODEAGENT_WEBHOOK_SECRET", raising=False)
    body = b'hello'
    assert _verify_webhook_signature(body, _sig(body, "anything")) is False


def test_webhook_missing_or_bad_sig_header(monkeypatch):
    monkeypatch.setenv("CODEAGENT_WEBHOOK_SECRET", "secret-1")
    body = b'hello'
    assert _verify_webhook_signature(body, None) is False
    assert _verify_webhook_signature(body, "md5=abc") is False  # 非 sha256=


# ---------- _listens_on_all_interfaces ----------
@pytest.mark.parametrize("host", ["0.0.0.0", "::", "*", ""])
def test_listens_all_interfaces_true(host):
    assert _listens_on_all_interfaces(host) is True


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "192.168.1.5"])
def test_listens_all_interfaces_false(host):
    assert _listens_on_all_interfaces(host) is False


# ---------- _auto_continue_nudge ----------
def test_nudge_no_meta_returns_default():
    out = _auto_continue_nudge(None)
    assert out == _auto_continue_nudge({})


def test_nudge_with_domain_playbook():
    out = _auto_continue_nudge({
        "failure_domain": "bash",
        "failure_streak": 3,
        "recent_errors": [{"tool": "bash", "error": "timeout"}],
    })
    assert "策略切换触发" in out
    assert "`bash`" in out
    assert "timeout" in out


def test_nudge_unknown_domain_falls_back():
    out = _auto_continue_nudge({"failure_domain": "unknown_dom", "failure_streak": 2})
    assert "策略切换触发" not in out  # 无 playbook → 回退默认


def test_nudge_truncates_long_error():
    long_err = "e" * 500
    out = _auto_continue_nudge({
        "failure_domain": "file_",
        "failure_streak": 2,
        "recent_errors": [{"tool": "file_read", "error": long_err}],
    })
    assert "…" in out  # 超长错误被截断


# ---------- _webui_history_partition_user_blocks ----------
def test_partition_basic():
    rows = [
        {"role": "user"}, {"role": "assistant"},
        {"role": "user"}, {"role": "assistant"}, {"role": "assistant"},
    ]
    blocks = _webui_history_partition_user_blocks(rows)
    assert len(blocks) == 2
    assert blocks[0][0]["role"] == "user"
    assert blocks[1][0]["role"] == "user"
    assert len(blocks[1]) == 3  # user + 2 assistant


def test_partition_empty():
    assert _webui_history_partition_user_blocks([]) == []


def test_partition_single_user():
    assert _webui_history_partition_user_blocks([{"role": "user"}]) == [[{"role": "user"}]]


def test_partition_leading_assistant_goes_to_first_block():
    rows = [{"role": "assistant"}, {"role": "user"}, {"role": "assistant"}]
    blocks = _webui_history_partition_user_blocks(rows)
    assert len(blocks) == 2
    assert blocks[0][0]["role"] == "assistant"  # 孤立 assistant 自成一块


# ---------- _running_* 线程安全集合 ----------
def test_running_add_contains_discard():
    _running_discard("agent::sess")
    assert _running_contains("agent::sess") is False
    _running_add("agent::sess")
    assert _running_contains("agent::sess") is True
    _running_discard("agent::sess")
    assert _running_contains("agent::sess") is False


def test_running_list_filters_by_agent():
    _running_discard("a::s1")
    _running_discard("b::s2")
    _running_add("a::s1")
    _running_add("b::s2")
    assert _running_list("a") == ["s1"]
    assert _running_list("b") == ["s2"]
    _running_discard("a::s1")
    _running_discard("b::s2")
