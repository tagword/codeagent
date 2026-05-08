"""Shared in-memory session state used by server and cron scheduler.

This belongs in seed (engine) because both the server and cron_sched need
access to the same live sessions dict. Putting it in codeagent would create
a reverse dependency.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Set

from seed.models import Session

# In-memory session cache, keyed by _memkey(agent_id, session_id)
SESSIONS: Dict[str, Session] = {}
# Active WebSocket connections by session key
WS_BY_SESSION: DefaultDict[str, Set[Any]] = defaultdict(set)
# Cancel events for active chats
ACTIVE_CHAT_CANCELS: Dict[str, threading.Event] = {}


def _memkey(agent_id: str, session_id: str) -> str:
    return f"{(agent_id or 'default').strip() or 'default'}::{session_id}"
