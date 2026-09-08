"""codeagent.server.self_healing 配置解析单元测试。

覆盖 _env_bool / _env_int / _heartbeat_timeout / watchdog_interval / is_enabled 的边界。
"""
import pytest

from codeagent.server import self_healing as sh


# ---------- _env_bool ----------
def test_env_bool_missing_uses_default(monkeypatch):
    monkeypatch.delenv("CA_SH_TEST", raising=False)
    assert sh._env_bool("CA_SH_TEST", True) is True
    assert sh._env_bool("CA_SH_TEST", False) is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "On"])
def test_env_bool_true_values(monkeypatch, val):
    monkeypatch.setenv("CA_SH_TEST", val)
    assert sh._env_bool("CA_SH_TEST", False) is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "banana"])
def test_env_bool_false_or_invalid(monkeypatch, val):
    monkeypatch.setenv("CA_SH_TEST", val)
    # banana 未知 → 回退默认
    if val == "banana":
        assert sh._env_bool("CA_SH_TEST", True) is True
    else:
        assert sh._env_bool("CA_SH_TEST", True) is False


# ---------- _env_int ----------
def test_env_int_missing_uses_default(monkeypatch):
    monkeypatch.delenv("CA_SH_TEST", raising=False)
    assert sh._env_int("CA_SH_TEST", 50, min_value=10, max_value=100) == 50


def test_env_int_valid(monkeypatch):
    monkeypatch.setenv("CA_SH_TEST", "75")
    assert sh._env_int("CA_SH_TEST", 50, min_value=10, max_value=100) == 75


def test_env_int_clamped_low(monkeypatch):
    monkeypatch.setenv("CA_SH_TEST", "5")
    assert sh._env_int("CA_SH_TEST", 50, min_value=10, max_value=100) == 10


def test_env_int_clamped_high(monkeypatch):
    monkeypatch.setenv("CA_SH_TEST", "500")
    assert sh._env_int("CA_SH_TEST", 50, min_value=10, max_value=100) == 100


def test_env_int_invalid_uses_default(monkeypatch):
    monkeypatch.setenv("CA_SH_TEST", "abc")
    assert sh._env_int("CA_SH_TEST", 50, min_value=10, max_value=100) == 50


# ---------- _heartbeat_timeout ----------
def test_heartbeat_timeout_default(monkeypatch):
    monkeypatch.delenv("CODEAGENT_HEARTBEAT_TIMEOUT", raising=False)
    assert sh._heartbeat_timeout() == sh._DEFAULT_HEARTBEAT_TIMEOUT


def test_heartbeat_timeout_clamped(monkeypatch):
    monkeypatch.setenv("CODEAGENT_HEARTBEAT_TIMEOUT", "5")  # 低于 min 10
    assert sh._heartbeat_timeout() == 10
    monkeypatch.setenv("CODEAGENT_HEARTBEAT_TIMEOUT", "99999")  # 高于 max 3600
    assert sh._heartbeat_timeout() == 3600


# ---------- watchdog_interval ----------
def test_watchdog_interval_default(monkeypatch):
    monkeypatch.delenv("CODEAGENT_WATCHDOG_INTERVAL", raising=False)
    assert sh.watchdog_interval() == sh._DEFAULT_WATCHDOG_INTERVAL


# ---------- is_enabled ----------
def test_is_enabled_default(monkeypatch):
    monkeypatch.delenv("CODEAGENT_SELF_HEALING_ENABLED", raising=False)
    assert sh.is_enabled() == sh._DEFAULT_SELF_HEALING_ENABLED


def test_is_enabled_env_override(monkeypatch):
    monkeypatch.setenv("CODEAGENT_SELF_HEALING_ENABLED", "0")
    assert sh.is_enabled() is False
    monkeypatch.setenv("CODEAGENT_SELF_HEALING_ENABLED", "1")
    assert sh.is_enabled() is True
