"""P0 回归测试：空壳 agent 不得注册进 AgentRegistry。

复现的真实缺陷：
  磁盘上存在 persona/ 目录但**没有任何 persona 文件**的 agent（如
  ag_09e0fc0a7e6f42cc），旧实现 `_discover_agent_ids` 仅检查目录存在，
  于是把它注册进 registry → `list_agents` 工具返回它 → LLM 调它 →
  拿到空 persona 的默认行为 → **对使用者撒谎**（"看得见调不动"）。

本测试在修复前应失败（旧实现注册空壳），修复后通过。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codeagent.runtime.agent_bootstrap import _discover_agent_ids


@pytest.fixture()
def agents_root(tmp_path):
    root = tmp_path / "agents"
    root.mkdir()
    return root


def test_empty_persona_dir_not_discovered(agents_root):
    """persona/ 目录存在但无 *.md → 不算合格 agent（核心反例）。"""
    (agents_root / "hollow" / "persona").mkdir(parents=True)
    with patch(
        "codeagent.server.webui_handlers_agentmeta._agents_dir",
        return_value=agents_root,
    ):
        ids = _discover_agent_ids()
    assert "hollow" not in ids, "空 persona 的 agent 不应被注册（会误导 LLM）"


def test_persona_with_file_discovered(agents_root):
    """persona/ 下有 identity.md → 正常发现（happy path 仍成立）。"""
    pdir = agents_root / "real" / "persona"
    pdir.mkdir(parents=True)
    (pdir / "identity.md").write_text("# Identity\n", encoding="utf-8")
    with patch(
        "codeagent.server.webui_handlers_agentmeta._agents_dir",
        return_value=agents_root,
    ):
        ids = _discover_agent_ids()
    assert "real" in ids


def test_mixed_hollow_and_real(agents_root):
    """混合场景：只发现合格者，空壳被排除。"""
    (agents_root / "hollow1" / "persona").mkdir(parents=True)
    (agents_root / "hollow2" / "persona").mkdir(parents=True)
    pdir = agents_root / "ok" / "persona"
    pdir.mkdir(parents=True)
    (pdir / "soul.md").write_text("# Soul\n", encoding="utf-8")
    with patch(
        "codeagent.server.webui_handlers_agentmeta._agents_dir",
        return_value=agents_root,
    ):
        ids = _discover_agent_ids()
    assert ids == ["ok"]


def test_zero_byte_persona_not_discovered(agents_root):
    """persona/ 下有 *.md 但为 0 字节 → 仍是空壳，不得注册（真实案例 ag_09e0...）。"""
    pdir = agents_root / "emptyfile" / "persona"
    pdir.mkdir(parents=True)
    (pdir / "system.md").write_text("", encoding="utf-8")
    with patch(
        "codeagent.server.webui_handlers_agentmeta._agents_dir",
        return_value=agents_root,
    ):
        ids = _discover_agent_ids()
    assert "emptyfile" not in ids, "0 字节 persona 文件等同空壳，不得注册"


def test_nonempty_persona_discovered(agents_root):
    """有实质内容的 persona 文件 → 正常发现。"""
    pdir = agents_root / "real" / "persona"
    pdir.mkdir(parents=True)
    (pdir / "system.md").write_text("You are helpful.", encoding="utf-8")
    with patch(
        "codeagent.server.webui_handlers_agentmeta._agents_dir",
        return_value=agents_root,
    ):
        ids = _discover_agent_ids()
    assert "real" in ids


def test_no_persona_dir_still_excluded(agents_root):
    """无 persona/ 目录的目录仍被排除（既有行为不回归）。"""
    (agents_root / "bare").mkdir()
    with patch(
        "codeagent.server.webui_handlers_agentmeta._agents_dir",
        return_value=agents_root,
    ):
        ids = _discover_agent_ids()
    assert ids == []
