"""Shared agent/team metadata helpers — split out of ``webui_api_app``.

These pure filesystem helpers (`_agents_dir`, `_list_agent_metas`, `_teams_dir`,
`_list_team_metas`, `_read_agent_file`, `_write_agent_file`) are used by the
agents and teams route modules. Agent ids are sanitized against path traversal.
"""

from __future__ import annotations

import json
from pathlib import Path


def _agents_dir() -> Path:
    """Return the agents root directory (~/.codeagent/agents)."""
    from codeagent.core.paths import codeagent_home
    return codeagent_home() / "agents"


def _list_agent_metas() -> list[dict]:
    """Scan all agents on the filesystem and return metadata list."""
    ad = _agents_dir()
    if not ad.is_dir():
        return []
    agents: list[dict] = []
    for entry in sorted(ad.iterdir()):
        if not entry.is_dir():
            continue
        persona_dir = entry / "persona"
        if not persona_dir.is_dir():
            continue
        agent_id = entry.name
        # Read description
        desc_file = entry / "description.txt"
        description = desc_file.read_text(encoding="utf-8").strip() if desc_file.is_file() else ""
        # Read system prompt
        sys_file = persona_dir / "system.md"
        system_prompt = sys_file.read_text(encoding="utf-8") if sys_file.is_file() else ""
        # Read tools.json (runtime may fall back to "all tools" when absent)
        tools = {}
        tools_configured = False
        tools_file = entry / "tools.json"
        if tools_file.is_file():
            try:
                tools = json.loads(tools_file.read_text(encoding="utf-8"))
                tools_configured = True
            except (json.JSONDecodeError, OSError):
                tools = {}
        agents.append({
            "id": agent_id,
            "name": agent_id,
            "description": description,
            "system_prompt": system_prompt,
            "tools": tools,
            "tools_configured": tools_configured,
        })
    return agents


def _teams_dir() -> Path:
    """Return the teams root directory (~/.codeagent/teams)."""
    from codeagent.core.paths import codeagent_home
    return codeagent_home() / "teams"


def _list_team_metas() -> list[dict]:
    """Scan all teams and return metadata list."""
    td = _teams_dir()
    if not td.is_dir():
        return []
    teams: list[dict] = []
    for entry in sorted(td.iterdir()):
        if entry.suffix != ".json":
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            data["id"] = entry.stem
            teams.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return teams


def _read_agent_file(agent_id: str, *rel_parts: str) -> str | None:
    """Read a file inside an agent's directory if it exists.

    agent_id 用户可控，先净化防路径穿越（含 ../ 或 / 则拒绝）。
    """
    from codeagent.core.paths import _sanitize_agent_id

    safe_id = _sanitize_agent_id(agent_id)
    if not safe_id:
        return None
    p = _agents_dir() / safe_id
    for part in rel_parts:
        p = p / part
    try:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return None


def _write_agent_file(agent_id: str, content: str, *rel_parts: str) -> bool:
    """Write a file inside an agent's directory. Returns True on success.

    agent_id 用户可控，先净化防路径穿越（含 ../ 或 / 则拒绝）。
    """
    from codeagent.core.paths import _sanitize_agent_id

    safe_id = _sanitize_agent_id(agent_id)
    if not safe_id:
        return False
    p = _agents_dir() / safe_id
    for part in rel_parts:
        p = p / part
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False

