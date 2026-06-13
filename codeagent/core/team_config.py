"""Team configuration — parse .codeagent/config/team.json into typed data objects.

Usage::
    config = TeamConfig.from_file(".codeagent/config/team.json")
    lead = config.lead
    for member in config.members:
        print(member.id, member.name)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default team tools auto-injected into Lead
TEAM_TOOLS = ["call_agent", "dispatch", "parallel"]


@dataclass
class AgentConfig:
    """Configuration for a single agent (lead or member)."""

    id: str
    name: str
    persona: str
    tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> AgentConfig:
        """Create from parsed JSON dict."""
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            persona=d.get("persona", ""),
            tools=d.get("tools", []),
            metadata=d.get("metadata", {}),
        )


@dataclass
class TeamConfig:
    """Complete team configuration parsed from team.json."""

    version: str = "1.0"
    lead: Optional[AgentConfig] = None
    members: List[AgentConfig] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path | str) -> TeamConfig:
        """Parse a team.json file into a TeamConfig instance.

        Args:
            path: Path to team.json file.

        Returns:
            TeamConfig instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is invalid JSON or missing required fields.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Team config not found: {path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in team config: {e}")

        return cls.from_dict(data, config_dir=path.parent)

    @classmethod
    def from_dict(cls, data: dict, config_dir: Optional[Path] = None) -> TeamConfig:
        """Create from parsed JSON dict, with optional base dir for persona paths."""
        version = data.get("version", "1.0")
        metadata = data.get("metadata", {})

        lead_data = data.get("lead")
        if not lead_data:
            raise ValueError("team.json: 'lead' is required")

        lead = AgentConfig.from_dict(lead_data)
        # Auto-inject team tools to Lead
        for tool in TEAM_TOOLS:
            if tool not in lead.tools:
                lead.tools.append(tool)

        # Resolve lead persona path
        lead.persona = _resolve_path(lead.persona, config_dir)

        members = []
        for m in data.get("members", []):
            agent = AgentConfig.from_dict(m)
            agent.persona = _resolve_path(agent.persona, config_dir)
            members.append(agent)

        config = cls(version=version, lead=lead, members=members, metadata=metadata)
        config._validate()
        return config

    def _validate(self) -> None:
        """Validate config for required fields and consistency."""
        errors: List[str] = []

        if not self.lead:
            errors.append("Lead agent is required")

        # Check for duplicate IDs
        ids = [self.lead.id] if self.lead else []
        for m in self.members:
            if m.id in ids:
                errors.append(f"Duplicate agent id: {m.id!r}")
            ids.append(m.id)

        # Check persona files exist (warn, not error — they'll use defaults)
        all_agents = [self.lead] + self.members if self.lead else self.members
        for agent in all_agents:
            if agent.persona:
                p = Path(agent.persona)
                if not p.is_file():
                    logger.warning(f"Persona file not found for '{agent.id}': {agent.persona} — will use defaults")

        if errors:
            raise ValueError("Invalid team config:\n" + "\n".join(errors))

    def as_dict(self) -> dict:
        """Serialize back to dict (for debugging / display)."""
        return {
            "version": self.version,
            "lead": {
                "id": self.lead.id,
                "name": self.lead.name,
                "persona": self.lead.persona,
                "tools": self.lead.tools,
            } if self.lead else None,
            "members": [
                {
                    "id": m.id,
                    "name": m.name,
                    "persona": m.persona,
                    "tools": m.tools,
                }
                for m in self.members
            ],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.as_dict(), indent=indent, ensure_ascii=False)


def _resolve_path(persona_path: str, config_dir: Optional[Path]) -> str:
    """Resolve a persona path relative to config dir if it's a relative path."""
    if not persona_path or not config_dir:
        return persona_path
    p = Path(persona_path)
    if not p.is_absolute():
        resolved = (config_dir / p).resolve()
        return str(resolved)
    return persona_path


def create_default_team_config(config_dir: Path) -> TeamConfig:
    """Create a default team.json with standard 8-member roles.

    Args:
        config_dir: The .codeagent/config directory path.

    Returns:
        A TeamConfig with default roles.
    """
    # Persona paths relative to config dir
    def persona(name: str) -> str:
        return str(config_dir / ".." / "personas" / f"{name}.md")

    data = {
        "version": "1.0",
        "lead": {
            "id": "lead",
            "name": "Lead Developer",
            "persona": persona("lead"),
            "tools": [
                "file_read", "file_write", "file_edit_tool",
                "bash_exec", "git", "grep_tool", "glob_tool",
            ],
        },
        "members": [
            {
                "id": "pm",
                "name": "产品经理",
                "persona": persona("pm"),
                "tools": ["file_read", "file_write", "web_search"],
            },
            {
                "id": "ux_designer",
                "name": "UX 设计师",
                "persona": persona("ux-designer"),
                "tools": ["file_read", "file_write", "browser_screenshot"],
            },
            {
                "id": "frontend_dev",
                "name": "前端工程师",
                "persona": persona("frontend"),
                "tools": ["file_read", "file_write", "bash_exec", "browser_screenshot"],
            },
            {
                "id": "backend_dev",
                "name": "后端工程师",
                "persona": persona("backend"),
                "tools": ["file_read", "file_write", "bash_exec", "db"],
            },
            {
                "id": "test_dev",
                "name": "测试工程师",
                "persona": persona("test"),
                "tools": ["file_read", "bash_exec", "test_run"],
            },
            {
                "id": "reviewer",
                "name": "代码审查员",
                "persona": persona("reviewer"),
                "tools": ["file_read", "code_check", "git"],
            },
            {
                "id": "doc_writer",
                "name": "文档工程师",
                "persona": persona("doc-writer"),
                "tools": ["file_read", "file_write", "bash_exec"],
            },
            {
                "id": "data_analyst",
                "name": "数据分析师",
                "persona": persona("data-analyst"),
                "tools": ["file_read", "bash_exec", "db"],
            },
        ],
    }
    return TeamConfig.from_dict(data, config_dir=config_dir)
