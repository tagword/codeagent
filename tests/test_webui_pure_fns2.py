"""codeagent.server.webui_api_app 纯函数单元测试。

覆盖 _split_git_args / _git_host_from_url / _parse_mcp_skill_slash_command。
"""
import pytest

from codeagent.server.webui_api_app import _parse_mcp_skill_slash_command
from codeagent.server.webui_handlers_git import _git_host_from_url, _split_git_args


# ---------- _split_git_args ----------
def test_split_git_args_string():
    assert _split_git_args("log --oneline -5") == ["log", "--oneline", "-5"]


def test_split_git_args_list():
    assert _split_git_args(["log", "-1"]) == ["log", "-1"]
    assert _split_git_args([1, "x"]) == ["1", "x"]


def test_split_git_args_empty():
    assert _split_git_args("") == []
    assert _split_git_args(None) == []


def test_split_git_args_quotes():
    # 引号内的空格保留
    assert _split_git_args('commit -m "hello world"') == ["commit", "-m", "hello world"]


# ---------- _git_host_from_url ----------
def test_git_host_https_url():
    assert _git_host_from_url("https://github.com/user/repo") == ("https", "github.com")


def test_git_host_no_scheme():
    assert _git_host_from_url("github.com/user/repo") == ("https", "github.com")


def test_git_host_empty():
    assert _git_host_from_url("") == ("https", "")


def test_git_host_ssh_scp_style():
    scheme, host = _git_host_from_url("git@github.com:user/repo.git")
    # scp 风格无 :// → 归为 https scheme
    assert scheme == "https"
    assert "github.com" in host


# ---------- _parse_mcp_skill_slash_command ----------
def test_parse_skill_long_form():
    assert _parse_mcp_skill_slash_command("/skill minimax do-something") == ("minimax", "do-something", "{}")


def test_parse_skill_long_form_with_args():
    assert _parse_mcp_skill_slash_command('/skill minimax do-something {"a":1}') == ("minimax", "do-something", '{"a":1}')


def test_parse_skill_short_form():
    assert _parse_mcp_skill_slash_command("/minimax:do-something") == ("minimax", "do-something", "{}")


def test_parse_skill_short_form_with_args():
    assert _parse_mcp_skill_slash_command('/minimax:do-something {"a":1}') == ("minimax", "do-something", '{"a":1}')


def test_parse_skill_short_form_with_slash_in_name():
    # skill 名含 / 的场景（用 server:name 解析）
    assert _parse_mcp_skill_slash_command("/minimax:skill/name") == ("minimax", "skill/name", "{}")


def test_parse_skill_invalid_raises():
    with pytest.raises(ValueError):
        _parse_mcp_skill_slash_command("普通文本")
    with pytest.raises(ValueError):
        _parse_mcp_skill_slash_command("/skill")
    with pytest.raises(ValueError):
        _parse_mcp_skill_slash_command("")
