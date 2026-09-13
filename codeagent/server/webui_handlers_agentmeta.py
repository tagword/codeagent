"""Shared agent/team metadata helpers — split out of ``webui_api_app``.

These pure filesystem helpers (`_agents_dir`, `_list_agent_metas`, `_teams_dir`,
`_list_team_metas`, `_read_agent_file`, `_write_agent_file`) are used by the
agents and teams route modules. Agent ids are sanitized against path traversal.
"""

from __future__ import annotations

import json
from pathlib import Path


def _agents_dir(project_root: Path | None = None) -> Path:
    """Return the agents root directory.

    Resolution order:

    1. ``project_root`` when given — this is the kernel data root injected by
       ``build_*_routes(project_root)`` (i.e. ``SEED_PROJECT_ROOT``). Agent
       *creation* (``ensure_agent_scaffold``) writes under this same root, so
       readers must use it too or newly created agents become invisible.
    2. ``codeagent_home()`` (``~/.codeagent``) as a fallback for callers that
       have no injected root.

    Historically this helper only used ``codeagent_home()``, which silently
    diverged from the write path whenever ``SEED_PROJECT_ROOT`` was set to a
    non-default location (e.g. an isolated RSI copy) — agents were created
    under ``$SEED_PROJECT_ROOT/agents`` yet listed from ``~/.codeagent/agents``.
    """
    if project_root is not None:
        return Path(project_root) / "agents"
    from codeagent.core.paths import codeagent_home
    return codeagent_home() / "agents"


def _list_agent_metas(project_root: Path | None = None) -> list[dict]:
    """Scan all agents on the filesystem and return metadata list."""
    ad = _agents_dir(project_root)
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


def _teams_dir(project_root: Path | None = None) -> Path:
    """Return the teams root directory (``<root>/teams``).

    See ``_agents_dir`` for why the injected ``project_root`` takes precedence.
    """
    if project_root is not None:
        return Path(project_root) / "teams"
    from codeagent.core.paths import codeagent_home
    return codeagent_home() / "teams"


def _list_team_metas(project_root: Path | None = None) -> list[dict]:
    """Scan all teams and return metadata list."""
    td = _teams_dir(project_root)
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


def _read_agent_file(
    agent_id: str, *rel_parts: str, project_root: Path | None = None
) -> str | None:
    """Read a file inside an agent's directory if it exists.

    agent_id 用户可控，先净化防路径穿越（含 ../ 或 / 则拒绝）。
    ``project_root`` 与写入端保持一致，避免读到与写入不同的目录。
    """
    from codeagent.core.paths import _sanitize_agent_id

    safe_id = _sanitize_agent_id(agent_id)
    if not safe_id:
        return None
    p = _agents_dir(project_root) / safe_id
    for part in rel_parts:
        p = p / part
    try:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return None


def _write_agent_file(
    agent_id: str, content: str, *rel_parts: str, project_root: Path | None = None
) -> bool:
    """Write a file inside an agent's directory. Returns True on success.

    agent_id 用户可控，先净化防路径穿越（含 ../ 或 / 则拒绝）。
    ``project_root`` 与读取端保持一致，避免写到列表看不到的目录。
    """
    from codeagent.core.paths import _sanitize_agent_id

    safe_id = _sanitize_agent_id(agent_id)
    if not safe_id:
        return False
    p = _agents_dir(project_root) / safe_id
    for part in rel_parts:
        p = p / part
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False

