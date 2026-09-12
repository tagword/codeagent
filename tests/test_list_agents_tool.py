"""Tests for the ``list_agents`` team tool (agent discoverability).

The gap this closes: the LLM could call ``call_agent`` but had no way to learn
which agent ids exist — users had to type ids manually. ``list_agents`` makes
the registry introspectable from chat.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from seed_tools.team import list_agents, list_agents_tool_def

from seed.core.agent_registry import AgentHandle, AgentRegistry


@pytest.fixture(autouse=True)
def _clean_registry():
    AgentRegistry.clear()
    yield
    AgentRegistry.clear()


class _StubAgent:
    """Minimal AgentHandle-compatible stub (only needs run_task)."""

    def __init__(self, aid: str):
        self.agent_id = aid

    def run_task(self, task: str) -> dict:
        return {"content": f"stub:{self.agent_id}", "success": True}


def _run(coro):
    return asyncio.run(coro)


def test_list_agents_empty_has_hint():
    out = json.loads(_run(list_agents()))
    assert out["agents"] == []
    assert "hint" in out and out["hint"]


def test_list_agents_returns_registered():
    AgentRegistry.register(
        "alpha",
        AgentHandle(agent=_StubAgent("alpha"), metadata={"source": "disk-bootstrap"}),
    )
    AgentRegistry.register(
        "beta",
        AgentHandle(agent=_StubAgent("beta"), metadata={"source": "disk-bootstrap"}),
    )
    out = json.loads(_run(list_agents()))
    ids = [a["agent_id"] for a in out["agents"]]
    assert ids == ["alpha", "beta"]  # sorted
    assert out["count"] == 2
    assert out["agents"][0]["source"] == "disk-bootstrap"


def test_list_agents_sorted_stable():
    for aid in ["zeta", "alpha", "mike"]:
        AgentRegistry.register(aid, AgentHandle(agent=_StubAgent(aid)))
    out = json.loads(_run(list_agents()))
    assert [a["agent_id"] for a in out["agents"]] == ["alpha", "mike", "zeta"]


def test_tool_def_shape():
    assert list_agents_tool_def.name == "list_agents"
    assert list_agents_tool_def.category == "team"
    assert list_agents_tool_def.parameters == {}
    assert "List all agents" in list_agents_tool_def.description


def test_call_agent_description_points_to_list_agents():
    """call_agent must tell the LLM to discover ids via list_agents first."""
    from seed_tools.team import call_agent_tool_def, dispatch_tool_def

    assert "list_agents" in call_agent_tool_def.description
    assert "list_agents" in dispatch_tool_def.description
