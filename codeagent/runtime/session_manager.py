"""Session manager placeholder for multi-agent/multi-session."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionManager:
    """
    v0: in-memory mapping.

    Phase 2+: add locking, per-agent namespaces, persistence policy, etc.
    """

    active_agent_by_session: dict[str, str]

    def __init__(self) -> None:
        self.active_agent_by_session = {}

    def set_active_agent(self, session_id: str, agent_id: str) -> None:
        self.active_agent_by_session[str(session_id)] = str(agent_id)

    def get_active_agent(self, session_id: str) -> str | None:
        return self.active_agent_by_session.get(str(session_id))

