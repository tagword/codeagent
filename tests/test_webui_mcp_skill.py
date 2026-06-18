"""WebUI MCP skill slash command parsing."""

from __future__ import annotations

import pytest

from codeagent.server.webui_api_app import _parse_mcp_skill_slash_command


def test_parse_skill_slash_command_with_json_args() -> None:
    sid, name, args = _parse_mcp_skill_slash_command('/skill docs summarize {"text":"hello"}')

    assert sid == "docs"
    assert name == "summarize"
    assert args == '{"text":"hello"}'


def test_parse_skill_slash_command_with_server_slash_skill() -> None:
    sid, name, args = _parse_mcp_skill_slash_command("/skill docs/summarize")

    assert sid == "docs"
    assert name == "summarize"
    assert args == "{}"


def test_parse_short_skill_slash_command() -> None:
    sid, name, args = _parse_mcp_skill_slash_command('/docs:summarize {"text":"hello"}')

    assert sid == "docs"
    assert name == "summarize"
    assert args == '{"text":"hello"}'


def test_parse_skill_slash_command_rejects_missing_skill() -> None:
    with pytest.raises(ValueError, match="usage"):
        _parse_mcp_skill_slash_command("/skill docs")
