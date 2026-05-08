"""Session persistence module - Save/load session data with token tracking"""

import json
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

# Default paths
CODEAGENT_DIR = os.path.expanduser("~/.codeagent")
SESSIONS_DIR = os.path.join(CODEAGENT_DIR, "sessions")

@dataclass
class SessionTokens:
    """Token usage tracking for a session"""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionTokens":
        return cls(input_tokens=data.get('input_tokens', 0), output_tokens=data.get('output_tokens', 0))

@dataclass
class SessionData:
    """Session state for persistence"""
    session_id: str
    messages: List[str]
    created_at: str
    updated_at: str
    metrics: Dict[str, int]
    tokens: Dict[str, int]
    turn_count: int
    
    @classmethod
    def from_session(cls, session, tokens_in: int, tokens_out: int) -> "SessionData":
        return cls(
            session_id=session.session_id,
            messages=session.messages,
            created_at=session.created_at.isoformat(),
            updated_at=datetime.now().isoformat(),
            metrics={"turn_count": session.turn_count, "messages": len(session.messages)},
            tokens={"input_tokens": tokens_in, "output_tokens": tokens_out},
            turn_count=session.turn_count
        )

def ensure_session_dir():
    """Ensure session directory exists"""
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def save_session(session_id: str, messages: List[str], tokens_in: int, tokens_out: int, auto_create: bool = True):
    """
    Save session data to file.
    
    Arguments:
        session_id: Unique session identifier
        messages: List of messages in the session
        tokens_in: Input token count
        tokens_out: Output token count
        auto_create: If True, create session dir if needed
    """
    if auto_create:
        ensure_session_dir()
    
    session_data = SessionData(
        session_id=session_id,
        messages=messages,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        metrics={'message_count': len(messages)},
        tokens={'input': tokens_in, 'output': tokens_out},
        turn_count=0
    )
    
    file_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(session_data), f, indent=2, ensure_ascii=False)
    
    return file_path


def load_session(session_id: str) -> Optional[SessionData]:
    """
    Load session data from file.
    
    Arguments:
        session_id: Unique session identifier
    
    Returns:
        SessionData if found, None otherwise
    """
    file_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return SessionData(**data)

def list_sessions() -> List[str]:
    """List all session IDs in the sessions directory."""
    ensure_session_dir()
    sessions = []
    for filename in os.listdir(SESSIONS_DIR):
        if filename.endswith('.json'):
            sessions.append(filename[:-5])  # Remove .json extension
    return sessions

def delete_session(session_id: str) -> bool:
    """Delete a session file."""
    file_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False

def load_all_sessions() -> List[SessionData]:
    """Load all session data."""
    ensure_session_dir()
    sessions = []
    for session_id in list_sessions():
        session = load_session(session_id)
        if session:
            sessions.append(session)
    return sessions