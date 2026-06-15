"""Tests for team_manager module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeagent.core.team_config import TeamConfig, create_default_team_config


# Simple stub agent for testing
class _StubAgent:
    def __init__(self, agent_id: str, persona: str, tools: list[str]):
        self.agent_id = agent_id
        self.persona = persona
        self.tools = tools

    def run_task(self, task: str) -> dict:
        return {"content": f"Stub result from {self.agent_id}"}


def _stub_create_agent(agent_id: str, persona: str, tools: list[str]):
    return _StubAgent(agent_id, persona, tools)


@pytest.fixture(autouse=True)
def reset_team(request):
    """Reset TeamManager singleton and AgentRegistry before each test."""
    from codeagent.core.team_manager import TeamManager
    TeamManager._reset()


class TestTeamManager:
    def test_init_from_config(self, tmp_path: Path):
        """TeamManager loads valid config successfully."""
        from codeagent.core.team_manager import TeamManager

        data = {
            "lead": {"id": "lead", "name": "Lead", "tools": ["file_read"]},
            "members": [
                {"id": "w1", "name": "Worker 1", "tools": ["file_write"]},
            ],
        }
        cfg_path = tmp_path / "team.json"
        cfg_path.write_text(json.dumps(data), encoding="utf-8")

        tm = TeamManager()
        result = tm.init_from_config(cfg_path)

        assert result is True
        assert tm.is_team_mode
        assert tm.config.lead.id == "lead"
        assert len(tm.config.members) == 1

    def test_init_from_config_missing_file(self):
        """Missing file returns False, not error."""
        from codeagent.core.team_manager import TeamManager

        tm = TeamManager()
        result = tm.init_from_config("/nonexistent/team.json")

        assert result is False
        assert not tm.is_team_mode

    def test_init_from_config_invalid_content(self, tmp_path: Path):
        """Invalid JSON returns False (graceful degradation)."""
        from codeagent.core.team_manager import TeamManager

        cfg_path = tmp_path / "team.json"
        cfg_path.write_text("not json", encoding="utf-8")

        tm = TeamManager()
        result = tm.init_from_config(cfg_path)

        assert result is False

    def test_register_members(self, tmp_path: Path):
        """register_members creates and registers agents."""
        from seed.core.agent_registry import AgentRegistry
        from codeagent.core.team_manager import TeamManager

        data = {
            "lead": {"id": "lead", "name": "Lead", "tools": ["file_read"]},
            "members": [
                {"id": "w1", "name": "Worker 1", "tools": ["file_write"]},
                {"id": "w2", "name": "Worker 2", "tools": ["bash"]},
            ],
        }
        cfg_path = tmp_path / "team.json"
        cfg_path.write_text(json.dumps(data), encoding="utf-8")

        tm = TeamManager()
        tm.init_from_config(cfg_path)
        count = tm.register_members(_stub_create_agent)

        assert count == 3  # lead + 2 members
        assert tm.get_lead() is not None
        assert len(tm.get_members()) == 2
        assert tm.get_agent("w1") is not None
        assert tm.get_agent("w2") is not None
        assert tm.get_agent("nonexistent") is None

    def test_register_no_config(self):
        """register_members without config returns 0."""
        from codeagent.core.team_manager import TeamManager

        tm = TeamManager()
        count = tm.register_members(_stub_create_agent)

        assert count == 0

    def test_unregister_all(self, tmp_path: Path):
        """unregister_all removes all agents."""
        from seed.core.agent_registry import AgentRegistry
        from codeagent.core.team_manager import TeamManager

        data = {
            "lead": {"id": "lead", "name": "Lead"},
            "members": [{"id": "w1", "name": "W1"}],
        }
        cfg_path = tmp_path / "team.json"
        cfg_path.write_text(json.dumps(data), encoding="utf-8")

        tm = TeamManager()
        tm.init_from_config(cfg_path)
        tm.register_members(_stub_create_agent)
        assert len(AgentRegistry.list()) == 2

        tm.unregister_all()
        assert len(AgentRegistry.list()) == 0

    def test_get_team_status_team_mode(self, tmp_path: Path):
        """get_team_status returns team info."""
        from codeagent.core.team_manager import TeamManager

        data = {
            "lead": {"id": "lead", "name": "Lead"},
            "members": [{"id": "w1", "name": "W1"}],
        }
        cfg_path = tmp_path / "team.json"
        cfg_path.write_text(json.dumps(data), encoding="utf-8")

        tm = TeamManager()
        tm.init_from_config(cfg_path)
        status = tm.get_team_status()

        assert status["mode"] == "team"
        assert status["total_agents"] == 2

    def test_get_team_status_single_mode(self):
        """get_team_status returns single mode when no config."""
        from codeagent.core.team_manager import TeamManager

        tm = TeamManager()
        status = tm.get_team_status()

        assert status["mode"] == "single"

    def test_singleton_behavior(self):
        """TeamManager is a singleton."""
        from codeagent.core.team_manager import TeamManager

        tm1 = TeamManager()
        tm2 = TeamManager()
        assert tm1 is tm2
