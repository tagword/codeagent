"""codeagent.server.webui_api_app agent/team metas 扫描单元测试。

覆盖 _list_agent_metas / _list_team_metas。
monkeypatch _agents_dir/_teams_dir 指向临时目录隔离。
"""
import json

import codeagent.server.webui_api_app as mod


def _mk_agent(tmp, aid, *, desc="", sys_prompt="", tools=None, corrupt_tools=False):
    ad = tmp / "agents" / aid
    persona = ad / "persona"
    persona.mkdir(parents=True)
    if desc:
        (ad / "description.txt").write_text(desc, encoding="utf-8")
    if sys_prompt:
        (persona / "system.md").write_text(sys_prompt, encoding="utf-8")
    if tools is not None:
        (ad / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    elif corrupt_tools:
        (ad / "tools.json").write_text("not-json", encoding="utf-8")
    return ad


def _patch_agents_dir(monkeypatch, tmp):
    monkeypatch.setattr(mod, "_agents_dir", lambda: tmp / "agents")


# ---------- _list_agent_metas ----------
def test_agents_empty_dir(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)
    assert mod._list_agent_metas() == []


def test_agents_missing_dir(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)  # agents 目录不存在
    assert mod._list_agent_metas() == []


def test_agents_scan_full(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)
    _mk_agent(tmp_path, "a1", desc="desc1", sys_prompt="sys1", tools={"bash": True})
    metas = mod._list_agent_metas()
    assert len(metas) == 1
    m = metas[0]
    assert m["id"] == "a1"
    assert m["name"] == "a1"
    assert m["description"] == "desc1"
    assert m["system_prompt"] == "sys1"
    assert m["tools"] == {"bash": True}
    assert m["tools_configured"] is True


def test_agents_skips_non_persona_dirs(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)
    (tmp_path / "agents" / "no-persona").mkdir(parents=True)  # 无 persona → 跳过
    _mk_agent(tmp_path, "a1", sys_prompt="s")
    metas = mod._list_agent_metas()
    assert [m["id"] for m in metas] == ["a1"]


def test_agents_corrupt_tools(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)
    _mk_agent(tmp_path, "a1", corrupt_tools=True)
    metas = mod._list_agent_metas()
    assert metas[0]["tools"] == {}
    assert metas[0]["tools_configured"] is False


def test_agents_no_tools_file(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)
    _mk_agent(tmp_path, "a1")
    metas = mod._list_agent_metas()
    assert metas[0]["tools"] == {}
    assert metas[0]["tools_configured"] is False


def test_agents_sorted(tmp_path, monkeypatch):
    _patch_agents_dir(monkeypatch, tmp_path)
    _mk_agent(tmp_path, "b2", sys_prompt="s")
    _mk_agent(tmp_path, "a1", sys_prompt="s")
    metas = mod._list_agent_metas()
    assert [m["id"] for m in metas] == ["a1", "b2"]  # 排序


# ---------- _list_team_metas ----------
def test_teams_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_teams_dir", lambda: tmp_path / "teams")
    assert mod._list_team_metas() == []


def test_teams_scan(tmp_path, monkeypatch):
    td = tmp_path / "teams"
    td.mkdir(parents=True)
    (td / "team1.json").write_text(json.dumps({"name": "T1"}), encoding="utf-8")
    # 非 json 文件跳过
    (td / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mod, "_teams_dir", lambda: td)
    teams = mod._list_team_metas()
    assert len(teams) == 1
    assert teams[0]["name"] == "T1"
    assert teams[0]["id"] == "team1"  # stem 注入 id


def test_teams_corrupt_json_skipped(tmp_path, monkeypatch):
    td = tmp_path / "teams"
    td.mkdir(parents=True)
    (td / "bad.json").write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(mod, "_teams_dir", lambda: td)
    assert mod._list_team_metas() == []
