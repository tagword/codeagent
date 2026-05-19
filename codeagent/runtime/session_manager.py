"""Session manager with per-session agent binding and locks."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SessionManager:
    """Track active agent per session; optional per-session locks."""

    active_agent_by_session: dict[str, str] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _session_locks: dict[str, threading.Lock] = field(default_factory=dict, repr=False)

    def set_active_agent(self, session_id: str, agent_id: str) -> None:
        with self._lock:
            self.active_agent_by_session[str(session_id)] = str(agent_id)

    def get_active_agent(self, session_id: str) -> str | None:
        with self._lock:
            return self.active_agent_by_session.get(str(session_id))

    def session_lock(self, session_id: str) -> threading.Lock:
        with self._lock:
            sid = str(session_id)
            if sid not in self._session_locks:
                self._session_locks[sid] = threading.Lock()
            return self._session_locks[sid]
