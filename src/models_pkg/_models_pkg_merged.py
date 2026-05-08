"""Core data models for CodeAgent - routing, tools, sessions, and turns."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid



def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -----------------------------------------------------------------------------
# Tool / command registry (claw-style + router)
# -----------------------------------------------------------------------------



@dataclass
class Session:
    """
from __future__ import annotations

    Full agent session: chat history (OpenAI-shaped dicts) and turn log.
    """

    id: str
    name: str
    created_at: str = ""
    updated_at: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    turns: List[AgentTurnResult] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str, config: Optional[Dict[str, Any]] = None) -> Session:
        now = _utc_iso()
        return cls(
            id=uuid.uuid4().hex,
            name=name,
            created_at=now,
            updated_at=now,
            messages=[],
            turns=[],
            config=dict(config or {}),
            metadata={},
        )

    @classmethod
    def for_llm_handle(cls, handle: str, slug_id: str) -> Session:
        """New LLM chat / HTTP session row keyed by filesystem-safe slug (same as JSON basename)."""
        now = _utc_iso()
        return cls(
            id=slug_id,
            name=handle,
            created_at=now,
            updated_at=now,
            messages=[],
            turns=[],
            config={"kind": "llm_chat"},
            metadata={},
        )

    def add_message(self, role: str, content: str, **extra: Any) -> None:
        msg: Dict[str, Any] = {"role": role, "content": content}
        if extra:
            msg.update(extra)
        self.messages.append(msg)
        self.updated_at = _utc_iso()

    def add_turn(self, turn: AgentTurnResult) -> None:
        self.turns.append(turn)
        self.updated_at = _utc_iso()

    def touch_updated(self) -> None:
        """Set updated_at to now (UTC ISO)."""
        self.updated_at = _utc_iso()


"""Core data models for CodeAgent - routing, tools, sessions, and turns."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid


# -----------------------------------------------------------------------------
# Tool / command registry (claw-style + router)
# -----------------------------------------------------------------------------



@dataclass
class Tool:
    """Declarative tool metadata for LLM schema and registration."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: str = "string"
    category: str = "builtin"
    version: str = "1.0"

@dataclass
class Command:
    """CLI-style routed command (first-token router)."""

    name: str
    description: str = ""
    aliases: List[str] = field(default_factory=list)

@dataclass
class CommandRoutingResult:
    matched: bool
    command: Optional[Command] = None
    command_args: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    error: Optional[str] = None

@dataclass
class PortingModule:
    """Legacy command/tool shell definition (execution.py)."""

    name: str
    description: str
    command: Optional[str] = None
    enabled: bool = True
    category: Optional[str] = None
    examples: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"PortingModule(name='{self.name}', command='{self.command}', category='{self.category}')"

@dataclass
class CommandEntry:
    """Individual command registry entry (routing.py)."""

    name: str
    description: str
    category: str
    help_text: Optional[str] = None
    enabled: bool = True

    def __repr__(self) -> str:
        return f"CommandEntry(name='{self.name}', category='{self.category}')"

@dataclass
class UsageMetrics:
    """Token usage for simple query engine."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_requests: int = 0
    sessions_count: int = 1

    def add_request(self, input_toks: int, output_toks: int) -> None:
        self.input_tokens += input_toks
        self.output_tokens += output_toks
        self.total_requests += 1

    def __repr__(self) -> str:
        return (
            f"UsageMetrics(input={self.input_tokens}, output={self.output_tokens}, "
            f"requests={self.total_requests})"
        )

@dataclass
class UsageSummary:
    """Aggregated usage for agent turns / sessions."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

@dataclass
class QueryTurnResult:
    status: str
    turn_type: str
    matched_commands: List[str] = field(default_factory=list)
    matched_tools: List[str] = field(default_factory=list)
    output: Optional[str] = None
    stop_reason: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "turn_type": self.turn_type,
            "matched_commands": self.matched_commands,
            "matched_tools": self.matched_tools,
            "output": self.output,
            "stop_reason": self.stop_reason,
            "error": self.error,
        }

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class TurnMatchedCommand:
    """Optional per-turn command match record (serialized in session JSON)."""

    name: str
    source_hint: str = ""
    payload: Any = None
    handled: bool = False

@dataclass
class AgentTurnResult:
    session_id: str
    messages: List[str] = field(default_factory=list)
    tokens: UsageSummary = field(default_factory=UsageSummary)
    matched_commands: List[TurnMatchedCommand] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
