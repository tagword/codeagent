"""codeagent.core.team_config 单元测试。

覆盖 TeamConfig.from_dict 解析、校验（lead 必需/重复 id）、
persona 路径相对解析、as_dict 序列化、AgentConfig 解析。
"""
import json

import pytest

from codeagent.core.team_config import AgentConfig, TeamConfig, _resolve_path


def _base_data():
    return {
        "version": "1.0",
        "lead": {"id": "lead", "name": "Lead", "persona": "personas/lead.md"},
        "members": [
            {"id": "m1", "name": "Member1", "persona": "personas/m1.md"},
        ],
    }


# ---------- AgentConfig ----------
def test_agent_config_from_dict():
    a = AgentConfig.from_dict({"id": "a1", "name": "Agent 1", "persona": "p.md", "tools": ["x"]})
    assert a.id == "a1"
    assert a.name == "Agent 1"
    assert a.persona == "p.md"
    assert a.tools == ["x"]


def test_agent_config_name_defaults_to_id():
    a = AgentConfig.from_dict({"id": "a1"})
    assert a.name == "a1"
    assert a.persona == ""
    assert a.tools == []


# ---------- TeamConfig.from_dict ----------
def test_from_dict_basic():
    cfg = TeamConfig.from_dict(_base_data())
    assert cfg.lead.id == "lead"
    assert len(cfg.members) == 1
    assert cfg.members[0].id == "m1"


def test_from_dict_lead_required():
    with pytest.raises(ValueError, match="lead"):
        TeamConfig.from_dict({"members": []})


def test_from_dict_auto_injects_team_tools_to_lead():
    cfg = TeamConfig.from_dict(_base_data())
    for tool in ("call_agent", "dispatch", "parallel"):
        assert tool in cfg.lead.tools


def test_from_dict_lead_tools_preserved():
    data = _base_data()
    data["lead"]["tools"] = ["file_read"]
    cfg = TeamConfig.from_dict(data)
    assert "file_read" in cfg.lead.tools
    for tool in ("call_agent", "dispatch", "parallel"):
        assert tool in cfg.lead.tools


def test_from_dict_duplicate_id_raises():
    data = {
        "lead": {"id": "lead", "persona": ""},
        "members": [
            {"id": "lead", "persona": ""},  # 与 lead 重复
        ],
    }
    with pytest.raises(ValueError, match="Duplicate"):
        TeamConfig.from_dict(data)


def test_from_dict_duplicate_member_id_raises():
    data = {
        "lead": {"id": "lead", "persona": ""},
        "members": [
            {"id": "m1", "persona": ""},
            {"id": "m1", "persona": ""},
        ],
    }
    with pytest.raises(ValueError, match="Duplicate"):
        TeamConfig.from_dict(data)


def test_from_dict_with_empty_members():
    cfg = TeamConfig.from_dict({"lead": {"id": "lead", "persona": ""}})
    assert cfg.lead.id == "lead"
    assert cfg.members == []


# ---------- _resolve_path ----------
def test_resolve_relative_persona(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    r = _resolve_path("personas/lead.md", cfg_dir)
    assert r == str((cfg_dir / "personas" / "lead.md").resolve())


def test_resolve_absolute_persona_unchanged():
    r = _resolve_path("/abs/path/lead.md", None)
    assert r == "/abs/path/lead.md"


def test_resolve_empty_persona_unchanged():
    assert _resolve_path("", None) == ""


# ---------- as_dict / to_json ----------
def test_as_dict_roundtrip():
    cfg = TeamConfig.from_dict(_base_data())
    d = cfg.as_dict()
    assert d["lead"]["id"] == "lead"
    assert d["members"][0]["id"] == "m1"


def test_to_json_valid_json():
    cfg = TeamConfig.from_dict(_base_data())
    parsed = json.loads(cfg.to_json())
    assert parsed["lead"]["id"] == "lead"
