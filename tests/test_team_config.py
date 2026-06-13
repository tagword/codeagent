"""Tests for team_config module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeagent.core.team_config import TeamConfig, create_default_team_config


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestTeamConfig:
    def test_parse_valid_config(self, tmp_path: Path):
        """Parse a minimal valid team.json."""
        data = {
            "version": "1.0",
            "lead": {"id": "lead", "name": "Lead", "tools": ["file_read"]},
            "members": [
                {"id": "worker", "name": "Worker", "tools": ["file_write"]},
            ],
        }
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        config = TeamConfig.from_file(cfg_path)

        assert config.version == "1.0"
        assert config.lead.id == "lead"
        assert config.lead.name == "Lead"
        # Team tools auto-injected
        assert "call_agent" in config.lead.tools
        assert "dispatch" in config.lead.tools
        assert "parallel" in config.lead.tools
        # Original tool preserved
        assert "file_read" in config.lead.tools
        # Members
        assert len(config.members) == 1
        assert config.members[0].id == "worker"

    def test_parse_duplicate_ids(self, tmp_path: Path):
        """Duplicate agent IDs raise ValueError."""
        data = {
            "lead": {"id": "lead", "name": "Lead"},
            "members": [
                {"id": "dup", "name": "Dup1"},
                {"id": "dup", "name": "Dup2"},
            ],
        }
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        with pytest.raises(ValueError, match="Duplicate agent id"):
            TeamConfig.from_file(cfg_path)

    def test_parse_missing_lead(self, tmp_path: Path):
        """Missing 'lead' field raises ValueError."""
        data = {"members": [{"id": "w", "name": "W"}]}
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        with pytest.raises(ValueError, match="lead.*required"):
            TeamConfig.from_file(cfg_path)

    def test_parse_missing_file(self, tmp_path: Path):
        """File not found raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            TeamConfig.from_file(tmp_path / "nonexistent.json")

    def test_parse_invalid_json(self, tmp_path: Path):
        """Invalid JSON content raises ValueError."""
        cfg_path = tmp_path / "team.json"
        cfg_path.write_text("not json", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid JSON"):
            TeamConfig.from_file(cfg_path)

    def test_team_tools_not_duplicated(self, tmp_path: Path):
        """If lead already has team tools, they are not duplicated."""
        data = {
            "lead": {"id": "lead", "name": "Lead", "tools": ["call_agent", "file_read"]},
            "members": [],
        }
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        config = TeamConfig.from_file(cfg_path)

        # call_agent should appear only once
        assert config.lead.tools.count("call_agent") == 1
        assert config.lead.tools.count("file_read") == 1

    def test_parse_missing_persona_warns(self, tmp_path: Path, caplog):
        """Missing persona file logs a warning but does not fail."""
        data = {
            "lead": {"id": "lead", "name": "Lead", "persona": "/nonexistent/path.md"},
            "members": [],
        }
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        import logging
        caplog.set_level(logging.WARNING)
        TeamConfig.from_file(cfg_path)

        assert "Persona file not found" in caplog.text

    def test_serialize_as_dict(self, tmp_path: Path):
        """as_dict() round-trips correctly."""
        data = {
            "version": "1.0",
            "lead": {"id": "lead", "name": "Lead", "tools": ["file_read"]},
            "members": [
                {"id": "w", "name": "Worker", "tools": ["file_write"]},
            ],
        }
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        config = TeamConfig.from_file(cfg_path)
        result = config.as_dict()

        assert result["version"] == "1.0"
        assert result["lead"]["id"] == "lead"
        # Team tools should be in serialized output
        assert "call_agent" in result["lead"]["tools"]
        assert len(result["members"]) == 1

    def test_to_json(self, tmp_path: Path):
        """to_json() produces valid JSON."""
        data = {
            "lead": {"id": "lead", "name": "Lead"},
            "members": [],
        }
        cfg_path = tmp_path / "team.json"
        _write_json(cfg_path, data)

        config = TeamConfig.from_file(cfg_path)
        json_str = config.to_json()

        parsed = json.loads(json_str)
        assert parsed["lead"]["id"] == "lead"

    def test_create_default_config(self, tmp_path: Path):
        """create_default_team_config produces valid config with 8 members."""
        config = create_default_team_config(tmp_path)

        assert config.lead.id == "lead"
        assert len(config.members) == 8
        # Check all member types exist
        member_ids = {m.id for m in config.members}
        expected = {"pm", "ux_designer", "frontend_dev", "backend_dev",
                     "test_dev", "reviewer", "doc_writer", "data_analyst"}
        assert member_ids == expected
        # All members have tools
        for m in config.members:
            assert len(m.tools) > 0
