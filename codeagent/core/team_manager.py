"""Team manager — singleton that manages team lifecycle.

Usage::

    from codeagent.core.team_manager import TeamManager
    tm = TeamManager()
    tm.init_from_config(".codeagent/config/team.json")
    
    # Later, when runtime is available:
    tm.register_members(session_factory, llm_executor)
    
    # Lookup:
    lead = tm.get_lead()
    members = tm.get_members()
    agent = tm.get_agent("frontend_dev")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from seed.core.agent_registry import AgentHandle, AgentRegistry

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TeamManager:
    """Singleton that manages team configuration and agent lifecycle."""

    _instance: Optional["TeamManager"] = None

    def __new__(cls) -> "TeamManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._reset_state()
        return cls._instance

    def _reset_state(self) -> None:
        """Reset internal state (called from __new__ and _reset)."""
        self._initialized = False
        self._config = None
        self._lead_handle = None
        self._member_handles: Dict[str, AgentHandle] = {}

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton for testing. Clears instance and registry."""
        from seed.core.agent_registry import AgentRegistry
        AgentRegistry.clear()
        cls._instance = None

    def init_from_config(self, config_path: Path | str) -> bool:
        """Load and parse team.json config.

        Args:
            config_path: Path to team.json file.

        Returns:
            True if loaded successfully, False if file not found or invalid.
        """
        from codeagent.core.team_config import TeamConfig

        path = Path(config_path)
        if not path.is_file():
            logger.info(f"No team config found at {config_path} — running in single-agent mode")
            return False

        try:
            self._config = TeamConfig.from_file(path)
            self._initialized = True
            logger.info(
                f"Loaded team config: Lead='{self._config.lead.name}', "
                f"{len(self._config.members)} members"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to load team config: {e} — running in single-agent mode")
            return False

    @property
    def is_team_mode(self) -> bool:
        """True if team config was loaded successfully."""
        return self._initialized and self._config is not None

    @property
    def config(self):
        """The loaded TeamConfig (None if not in team mode)."""
        return self._config

    def get_lead(self) -> Optional[AgentHandle]:
        """Return the registered Lead agent handle."""
        if self._lead_handle:
            return self._lead_handle
        # Fall back to registry lookup
        if self._config and self._config.lead:
            return AgentRegistry.get(self._config.lead.id)
        return None

    def get_members(self) -> List[AgentHandle]:
        """Return list of all registered member agent handles."""
        return list(self._member_handles.values())

    def get_agent(self, agent_id: str) -> Optional[AgentHandle]:
        """Look up a registered agent by id.

        Checks members first, then lead.
        """
        handle = self._member_handles.get(agent_id)
        if handle:
            return handle
        return AgentRegistry.get(agent_id)

    def register_members(
        self,
        create_agent: Callable[[str, str, List[str]], Any],
    ) -> int:
        """Register all member agents with AgentRegistry.

        This should be called once the runtime is available to create agents.

        Args:
            create_agent: Factory function(agent_id, persona_path, tools) -> object
                The returned object must be suitable for AgentHandle construction.
                Typically an AutonomousAgent instance or any callable that can
                be passed to AgentHandle(agent=...).

        Returns:
            Number of agents registered.
        """
        if not self._config:
            logger.warning("Cannot register members: no team config loaded")
            return 0

        count = 0
        # Register lead first
        if self._config.lead:
            try:
                agent_instance = create_agent(
                    self._config.lead.id,
                    self._config.lead.persona,
                    self._config.lead.tools,
                )
                handle = AgentHandle(
                    agent=agent_instance,
                    metadata={"role": "lead", "name": self._config.lead.name},
                )
                AgentRegistry.register(self._config.lead.id, handle)
                self._lead_handle = handle
                count += 1
                logger.info(f"Registered Lead agent: {self._config.lead.id}")
            except Exception as e:
                logger.error(f"Failed to register Lead agent '{self._config.lead.id}': {e}")

        # Register members
        for member in self._config.members:
            if member.id in self._member_handles:
                logger.warning(f"Member '{member.id}' already registered, skipping")
                continue
            try:
                agent_instance = create_agent(
                    member.id,
                    member.persona,
                    member.tools,
                )
                handle = AgentHandle(
                    agent=agent_instance,
                    metadata={"role": "member", "name": member.name},
                )
                AgentRegistry.register(member.id, handle)
                self._member_handles[member.id] = handle
                count += 1
                logger.info(f"Registered member agent: {member.id} ({member.name})")
            except Exception as e:
                logger.error(f"Failed to register member '{member.id}': {e}")

        logger.info(f"Team registration complete: {count} agents registered")
        return count

    def unregister_all(self) -> None:
        """Remove all registered agents from the registry."""
        if self._lead_handle:
            AgentRegistry.unregister(self._config.lead.id if self._config else "")
            self._lead_handle = None
        for agent_id in list(self._member_handles.keys()):
            AgentRegistry.unregister(agent_id)
        self._member_handles.clear()
        logger.info("All team agents unregistered")

    def get_team_status(self) -> dict:
        """Return a summary of team status for UI display."""
        if not self.is_team_mode:
            return {"mode": "single", "agents": []}

        agents = []
        if self._config and self._config.lead:
            agents.append({
                "id": self._config.lead.id,
                "name": self._config.lead.name,
                "role": "lead",
                "tools": self._config.lead.tools,
                "registered": self._lead_handle is not None,
            })
        if self._config:
            for m in self._config.members:
                agents.append({
                    "id": m.id,
                    "name": m.name,
                    "role": "member",
                    "tools": m.tools,
                    "registered": m.id in self._member_handles,
                })

        return {
            "mode": "team",
            "version": self._config.version if self._config else "1.0",
            "total_agents": len(agents),
            "registered_count": sum(1 for a in agents if a["registered"]),
            "agents": agents,
        }


def team_config_path() -> Path:
    """Return the default team config path (.codeagent/config/team.json in project root)."""
    from seed.core.config_plane import project_root

    root = project_root()
    return root / "config" / "team.json"


def is_team_configured() -> bool:
    """Check if team.json exists and is valid."""
    path = team_config_path()
    if not path.is_file():
        return False
    try:
        from codeagent.core.team_config import TeamConfig
        TeamConfig.from_file(path)
        return True
    except Exception:
        return False
