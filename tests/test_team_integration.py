"""Integration tests for team system — config → manager → registry → use."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seed.core.agent_registry import AgentRegistry, AgentHandle

TEST_TOOLS = ["file_read", "file_write", "bash", "git"]


class _StubAgent:
    """Simple agent stub that records calls for testing."""

    def __init__(self, agent_id: str, persona: str, tools: list[str]):
        self.agent_id = agent_id
        self.persona = persona
        self.tools = tools
        self.calls: list[str] = []

    def run_task(self, task: str) -> dict:
        self.calls.append(task)
        return {"content": f"Result from {self.agent_id}: {task[:50]}"}


def _stub_factory(agent_id: str, persona: str, tools: list[str]):
    return _StubAgent(agent_id, persona, tools)


@pytest.fixture(autouse=True)
def reset_all():
    """Reset TeamManager singleton and AgentRegistry before each test."""
    from codeagent.core.team_manager import TeamManager
    TeamManager._reset()


def test_full_flow_setup(tmp_path: Path):
    """Full flow: team.json → TeamManager → register → lookup."""
    from codeagent.core.team_config import TeamConfig
    from codeagent.core.team_manager import TeamManager

    data = {
        "version": "1.0",
        "lead": {
            "id": "lead",
            "name": "Lead Developer",
            "tools": TEST_TOOLS,
        },
        "members": [
            {
                "id": "frontend_dev",
                "name": "前端工程师",
                "tools": ["file_read", "file_write"],
            },
            {
                "id": "backend_dev",
                "name": "后端工程师",
                "tools": ["file_read", "bash"],
            },
        ],
    }
    cfg_path = tmp_path / "team.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    # Step 1: Parse config
    config = TeamConfig.from_file(cfg_path)
    assert config.lead.id == "lead"
    assert "call_agent" in config.lead.tools
    assert len(config.members) == 2

    # Step 2: Init manager
    tm = TeamManager()
    assert tm.init_from_config(cfg_path)
    assert tm.is_team_mode

    # Step 3: Register agents
    count = tm.register_members(_stub_factory)
    assert count == 3

    # Step 4: Lookup via registry directly
    lead = AgentRegistry.get("lead")
    assert lead is not None
    assert lead.is_same_process

    frontend = AgentRegistry.get("frontend_dev")
    assert frontend is not None
    backend = AgentRegistry.get("backend_dev")
    assert backend is not None

    # Step 5: Run tasks via AgentHandle
    result = frontend.run_task("Build login page")
    assert "Result from frontend_dev" in result

    result = backend.run_task("Build login API")
    assert "Result from backend_dev" in result

    # Step 6: Check task recording
    agent = frontend._agent
    assert agent.calls == ["Build login page"]


def test_dispatch_sequential_flow(tmp_path: Path):
    """Simulate sequential dispatch flow."""
    from codeagent.core.team_manager import TeamManager

    data = {
        "lead": {"id": "lead", "name": "Lead", "tools": ["file_read"]},
        "members": [
            {"id": "m1", "name": "M1", "tools": ["file_read"]},
            {"id": "m2", "name": "M2", "tools": ["file_read"]},
        ],
    }
    cfg_path = tmp_path / "team.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    tm = TeamManager()
    tm.init_from_config(cfg_path)
    tm.register_members(_stub_factory)

    m1 = tm.get_agent("m1")
    m2 = tm.get_agent("m2")

    # Simulate sequential: m1 first, pass result to m2
    r1 = m1.run_task("Task 1")
    assert "m1" in r1

    r2 = m2.run_task(f"Task 2 (based on: {r1[:50]})")
    assert "m2" in r2


def test_dispatch_parallel_flow(tmp_path: Path):
    """Simulate parallel dispatch flow."""
    from codeagent.core.team_manager import TeamManager

    data = {
        "lead": {"id": "lead", "name": "Lead"},
        "members": [
            {"id": "m1", "name": "M1"},
            {"id": "m2", "name": "M2"},
            {"id": "m3", "name": "M3"},
        ],
    }
    cfg_path = tmp_path / "team.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    tm = TeamManager()
    tm.init_from_config(cfg_path)
    tm.register_members(_stub_factory)

    tasks = [
        ("m1", "Task A"),
        ("m2", "Task B"),
        ("m3", "Task C"),
    ]

    results = []
    for agent_id, task in tasks:
        agent = tm.get_agent(agent_id)
        result = agent.run_task(task)
        results.append(result)

    assert len(results) == 3
    assert all(f"Result from {aid}" in r for aid, r in zip(["m1", "m2", "m3"], results))


def test_team_config_empty_members(tmp_path: Path):
    """Team with no members is valid."""
    from codeagent.core.team_manager import TeamManager

    data = {
        "lead": {"id": "lead", "name": "Lead", "tools": ["file_read"]},
        "members": [],
    }
    cfg_path = tmp_path / "team.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    tm = TeamManager()
    assert tm.init_from_config(cfg_path)
    tm.register_members(_stub_factory)

    lead = tm.get_lead()
    assert lead is not None
    assert len(tm.get_members()) == 0


def test_registry_list(tmp_path: Path):
    """Registry.list() returns all registered agents."""
    from codeagent.core.team_manager import TeamManager

    data = {
        "lead": {"id": "lead", "name": "Lead"},
        "members": [
            {"id": "m1", "name": "M1"},
            {"id": "m2", "name": "M2"},
        ],
    }
    cfg_path = tmp_path / "team.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    tm = TeamManager()
    tm.init_from_config(cfg_path)
    tm.register_members(_stub_factory)

    all_agents = AgentRegistry.list()
    assert "lead" in all_agents
    assert "m1" in all_agents
    assert "m2" in all_agents
    assert len(all_agents) == 3


def test_handle_metadata(tmp_path: Path):
    """AgentHandle metadata is set correctly."""
    from codeagent.core.team_manager import TeamManager

    data = {
        "lead": {"id": "lead", "name": "Lead"},
        "members": [{"id": "m1", "name": "Worker"}],
    }
    cfg_path = tmp_path / "team.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    tm = TeamManager()
    tm.init_from_config(cfg_path)
    tm.register_members(_stub_factory)

    lead = tm.get_lead()
    assert lead.metadata.get("role") == "lead"
    assert lead.metadata.get("name") == "Lead"

    member = tm.get_agent("m1")
    assert member.metadata.get("role") == "member"
    assert member.metadata.get("name") == "Worker"
