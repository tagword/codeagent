"""codeagent.core.env 环境变量解析单元测试。

覆盖 pick_default / pick_nonempty / pick_int / env_truthy / env_falsy / default_agent_id 的边界。
"""
import os

import pytest

from codeagent.core import env as ca_env


# ---------- pick_default ----------
def test_pick_default_returns_env_when_set(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "custom")
    assert ca_env.pick_default("default", "CA_TEST_KEY") == "custom"


def test_pick_default_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv("CA_TEST_KEY", raising=False)
    assert ca_env.pick_default("default", "CA_TEST_KEY") == "default"


# ---------- pick_nonempty ----------
def test_pick_nonempty_returns_stripped(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "  value  ")
    assert ca_env.pick_nonempty("CA_TEST_KEY") == "value"


def test_pick_nonempty_empty_when_blank(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "   ")
    assert ca_env.pick_nonempty("CA_TEST_KEY") == ""


def test_pick_nonempty_empty_when_missing(monkeypatch):
    monkeypatch.delenv("CA_TEST_KEY", raising=False)
    assert ca_env.pick_nonempty("CA_TEST_KEY") == ""


# ---------- pick_int ----------
def test_pick_int_valid(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "42")
    assert ca_env.pick_int(0, "CA_TEST_KEY") == 42


def test_pick_int_strips_whitespace(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "  7  ")
    assert ca_env.pick_int(0, "CA_TEST_KEY") == 7


def test_pick_int_non_numeric_returns_default(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "abc")
    assert ca_env.pick_int(5, "CA_TEST_KEY") == 5


def test_pick_int_missing_returns_default(monkeypatch):
    monkeypatch.delenv("CA_TEST_KEY", raising=False)
    assert ca_env.pick_int(9, "CA_TEST_KEY") == 9


def test_pick_int_negative_valid(monkeypatch):
    monkeypatch.setenv("CA_TEST_KEY", "-3")
    assert ca_env.pick_int(0, "CA_TEST_KEY") == -3


# ---------- env_truthy / env_falsy ----------
@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "On"])
def test_env_truthy_true_values(monkeypatch, val):
    monkeypatch.setenv("CA_TEST_KEY", val)
    assert ca_env.env_truthy("CA_TEST_KEY") is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "banana", ""])
def test_env_truthy_false_values(monkeypatch, val):
    monkeypatch.setenv("CA_TEST_KEY", val)
    assert ca_env.env_truthy("CA_TEST_KEY") is False


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "FALSE", "Off"])
def test_env_falsy_true_values(monkeypatch, val):
    monkeypatch.setenv("CA_TEST_KEY", val)
    assert ca_env.env_falsy("CA_TEST_KEY") is True


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "banana", ""])
def test_env_falsy_false_values(monkeypatch, val):
    monkeypatch.setenv("CA_TEST_KEY", val)
    assert ca_env.env_falsy("CA_TEST_KEY") is False


def test_env_truthy_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("CA_TEST_KEY", raising=False)
    assert ca_env.env_truthy("CA_TEST_KEY", "1") is True
    assert ca_env.env_truthy("CA_TEST_KEY", "0") is False


def test_env_falsy_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("CA_TEST_KEY", raising=False)
    # default 是"env 缺失时用于白名单匹配的原始值"
    # default="0"(falsy) → True；default="1"(truthy) → False
    assert ca_env.env_falsy("CA_TEST_KEY", "0") is True
    assert ca_env.env_falsy("CA_TEST_KEY", "1") is False


# ---------- default_agent_id ----------
def test_default_agent_id_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv(ca_env.AGENT_ID, raising=False)
    assert ca_env.default_agent_id() == "default"


def test_default_agent_id_returns_env(monkeypatch):
    monkeypatch.setenv(ca_env.AGENT_ID, "  copy9  ")
    assert ca_env.default_agent_id() == "copy9"
