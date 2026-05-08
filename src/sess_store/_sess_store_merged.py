"""Session persistence module for CodeAgent"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

class ResourceManager:
    """
from __future__ import annotations

    Manages the ~/.codeagent resource directory structure.
    Creates and maintains the config, sessions subdirs.
    """
    
    BASE_DIR = Path.home() / ".codeagent"
    CONFIG_FILE = BASE_DIR / "config.yaml"
    SESSIONS_DIR = BASE_DIR / "sessions"
    
    @staticmethod
    def ensure_structure() -> None:
        """Ensure the resource directory structure exists"""
        ResourceManager.BASE_DIR.mkdir(parents=True, exist_ok=True)
        ResourceManager.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create config file if it doesn't exist
        if not ResourceManager.CONFIG_FILE.exists():
            ResourceManager._create_default_config()
    
    @staticmethod
    def _create_default_config() -> None:
        """Create a default configuration file"""
        default_config = """# CodeAgent Configuration
# Modify these settings as needed

agent:
  name: "codeagent"
  max_turns: 8
  token_budget: 2000

session:
  persistence: true
  save_path: "~/.codeagent/sessions/"

logging:
  level: "INFO"
  format: "%(asctime)s - %(levelname)s - %(message)s"
"""
        with open(ResourceManager.CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(default_config)
        logger.info(f"Default config created: {ResourceManager.CONFIG_FILE}")


class SessionManager:
    """
    High-level manager that combines persistence and in-memory cache.
    """
    
    def __init__(self, base_path: str):
        """
        Initialize the session manager.
        
        Args:
            base_path: Base directory for sessions (required)
        """
        self.store = SessionStore(base_path)
        self.cache: Dict[str, Session] = {}
    
    def create_session(self, name: str, config: Optional[Dict] = None) -> Session:
        """
        Create and persist a new session.
        
        Args:
            name: Session name
            config: Optional configuration
        
        Returns:
            Created session
        """
        session = Session.create(name, config)
        self.store.save_session(session)
        self.cache[session.id] = session
        return session
    
    def get_session(self, session_id: str) -> Session:
        """
        Get a session from cache or disk.
        
        Args:
            session_id: Session ID
        
        Returns:
            Session object
        
        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if session_id in self.cache:
            return self.cache[session_id]
        
        session = self.store.load_session(session_id)
        self.cache[session_id] = session
        return session
    
    def update_session(self, session: Session) -> None:
        """
        Update a session and persist changes.
        
        Args:
            session: Updated session
        """
        self.cache[session.id] = session
        self.store.save_session(session)
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID
        
        Returns:
            True if deleted
        """
        success = self.store.delete_session(session_id)
        if session_id in self.cache:
            del self.cache[session_id]
        return success
    
    def list_sessions(self) -> List[str]:
        """
        List all session IDs.
        
        Returns:
            List of session IDs
        """
        return self.store.list_sessions()
    
    def count_sessions(self) -> int:
        """
        Get count of sessions.
        
        Returns:
            Number of sessions
        """
        return self.store.count_sessions()
    
    def clear_cache(self) -> None:
        """Clear the in-memory cache"""
        self.cache = {}


"""Session persistence module for CodeAgent"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from src.models_pkg import Session, TurnResult, UsageSummary, TurnMatchedCommand


logger = logging.getLogger(__name__)


class SessionNotFoundError(Exception):
    """Exception raised when a session is not found"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session '{session_id}' not found")


class SessionPersistenceError(Exception):
    """Exception raised for session persistence errors"""
    
    def __init__(self, operation: str, path: str, error: str):
        self.operation = operation
        self.path = path
        self.error = error
        super().__init__(f"Session {operation} error at '{path}': {error}")




"""Session persistence module for CodeAgent"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Union

from src.models_pkg import Session, TurnMatchedCommand, TurnResult, UsageSummary

logger = logging.getLogger(__name__)


class SessionStore:
    """
    Manages persistence of sessions to the file system.
    Sessions are stored as JSON files in a dedicated directory.
    """

    def __init__(self, base_path: Union[str, Path]):
        if isinstance(base_path, str) and not base_path.strip():
            raise ValueError("SessionStore requires a non-empty base_path")
        self.base_path = Path(base_path).expanduser().resolve()
        self.sessions: Dict[str, Session] = {}
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            logger.debug("Session directory ensured: %s", self.base_path)
        except OSError as e:
            logger.error("Failed to create session directory: %s", e)
            raise SessionPersistenceError("create", str(self.base_path), str(e))

    def _session_to_dict(self, session: Session) -> Dict[str, Any]:
        turns_dict: List[Dict[str, Any]] = []
        for turn in session.turns:
            turns_dict.append(
                {
                    "session_id": turn.session_id,
                    "messages": turn.messages,
                    "tokens": {
                        "input_tokens": turn.tokens.input_tokens,
                        "output_tokens": turn.tokens.output_tokens,
                        "total_tokens": turn.tokens.total_tokens,
                    },
                    "matched_commands": [
                        {
                            "name": mc.name,
                            "source_hint": mc.source_hint,
                            "payload": mc.payload,
                            "handled": mc.handled,
                        }
                        for mc in turn.matched_commands
                    ],
                    "error": turn.error,
                    "metadata": turn.metadata,
                }
            )
        return {
            "id": session.id,
            "name": session.name,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "messages": session.messages,
            "turns": turns_dict,
            "config": session.config,
            "metadata": session.metadata,
        }

    def _dict_to_session(self, data: Dict[str, Any], *, fallback_id: str = "") -> Session:
        sid = str(data.get("id") or fallback_id or "")
        if not sid:
            raise ValueError("session JSON missing id")

        turns: List[TurnResult] = []
        for turn_dict in data.get("turns") or []:
            if not isinstance(turn_dict, dict):
                continue
            tok = turn_dict.get("tokens") or {}
            tokens = UsageSummary(
                input_tokens=int(tok.get("input_tokens", 0)),
                output_tokens=int(tok.get("output_tokens", 0)),
            )
            matched_commands = []
            for mc in turn_dict.get("matched_commands") or []:
                if not isinstance(mc, dict):
                    continue
                matched_commands.append(
                    TurnMatchedCommand(
                        name=str(mc.get("name") or ""),
                        source_hint=str(mc.get("source_hint") or ""),
                        payload=mc.get("payload"),
                        handled=bool(mc.get("handled", False)),
                    )
                )
            raw_msgs = turn_dict.get("messages")
            if isinstance(raw_msgs, list):
                messages_list = [m if isinstance(m, str) else str(m) for m in raw_msgs]
            else:
                messages_list = []
            turns.append(
                TurnResult(
                    session_id=str(turn_dict.get("session_id") or sid),
                    messages=messages_list,
                    tokens=tokens,
                    matched_commands=matched_commands,
                    error=turn_dict.get("error"),
                    metadata=dict(turn_dict.get("metadata") or {}),
                )
            )

        raw_msgs = data.get("messages")
        if isinstance(raw_msgs, list):
            chat_messages = [m for m in raw_msgs if isinstance(m, dict)]
        else:
            chat_messages = []

        return Session(
            id=sid,
            name=str(data.get("name") or "Untitled Session"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            messages=chat_messages,
            turns=turns,
            config=dict(data.get("config") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def save_session(self, session: Session) -> str:
        file_path = self.base_path / f"{session.id}.json"
        temp_path = self.base_path / f".tmp_{session.id}.json"

        try:
            payload = self._session_to_dict(session)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
            temp_path.replace(file_path)
            logger.info("Session saved: %s -> %s", session.id, file_path)
            return str(file_path)
        except Exception as e:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise SessionPersistenceError("save", str(file_path), str(e))

    def load_session(self, session_id: str) -> Session:
        file_path = self.base_path / f"{session_id}.json"

        if not file_path.exists():
            raise SessionNotFoundError(session_id)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise SessionPersistenceError("load", str(file_path), "root must be a JSON object")
            session = self._dict_to_session(data, fallback_id=session_id)
            logger.info("Session loaded: %s from %s", session_id, file_path)
            return session
        except json.JSONDecodeError as e:
            raise SessionPersistenceError("load", str(file_path), f"Invalid JSON: {e}")
        except OSError as e:
            raise SessionPersistenceError("load", str(file_path), str(e))

    def delete_session(self, session_id: str) -> bool:
        file_path = self.base_path / f"{session_id}.json"

        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            logger.info("Session deleted: %s", session_id)
            return True
        except OSError as e:
            logger.error("Failed to delete session: %s", e)
            return False

    def list_sessions(self) -> List[str]:
        """Return session ids that have a persisted JSON file."""
        ids: List[str] = []
        try:
            for p in sorted(self.base_path.glob("*.json")):
                if p.is_file():
                    ids.append(p.stem)
        except OSError as e:
            logger.error("Failed to list sessions: %s", e)
        return ids

    def count_sessions(self) -> int:
        return len(self.list_sessions())
