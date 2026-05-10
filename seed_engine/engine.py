"""Turn loop engine with state management"""

from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime
import os

from seed_engine.models import QueryTurnResult, UsageMetrics
from .routing import find_commands
from .persistence import save_session, SESSIONS_DIR

DEFAULT_MAX_TURNS = 8
DEFAULT_BUDGET_TOKENS = 2000
DEFAULT_COMPACT_AFTER = 12


@dataclass
class EngineConfig:
    max_turns: int = DEFAULT_MAX_TURNS
    token_budget: int = DEFAULT_BUDGET_TOKENS
    compact_after: int = DEFAULT_COMPACT_AFTER
    auto_save_dir: Optional[str] = None
    session_id: Optional[str] = None


class QueryEngine:
    """
    Stateful turn loop engine for codeagent.
    Handles message routing, token tracking, and session management.
    """

    def __init__(self, config: Optional[EngineConfig] = None, session_id: Optional[str] = None):
        self.config = config or EngineConfig()
        self.session_id = session_id or "session"
        self.message_history: List[str] = []
        self.turn_results: List[QueryTurnResult] = []
        self.metrics = UsageMetrics()
        self.turn_count = 0
        self.is_terminated = False
        self.token_input = 0
        self.token_output = 0

    def submit_message(self, message: str, turn_limit: Optional[int] = None) -> QueryTurnResult:
        """Process a message through the turn loop."""
        # Check termination
        if self.is_terminated:
            return QueryTurnResult(
                status='terminated',
                turn_type='turn',
                matched_commands=[],
                stop_reason='session_terminated',
                error="Session already terminated"
            )

        # Check turn limit
        effective_limit = turn_limit or self.config.max_turns
        if self.turn_count >= effective_limit:
            self.is_terminated = True
            return QueryTurnResult(
                status='stop',
                turn_type='max_turns',
                matched_commands=[],
                stop_reason='max_turns_reached'
            )

        # Check budget
        if self.token_input + self.token_output > self.config.token_budget:
            self.is_terminated = True
            return QueryTurnResult(
                status='stop',
                turn_type='budget',
                matched_commands=[],
                stop_reason='budget_exceeded'
            )

        # Add message to history
        self.message_history.append(message)
        self.turn_count += 1

        # Find matching commands
        matched = find_commands(message, limit=5)
        matches = [m.name for m in matched if hasattr(m, 'name')]

        # Create result
        return QueryTurnResult(
            status='success',
            turn_type='prompt',
            matched_commands=matches,
            output=message,
            stop_reason=None
        )

    def persist_session(self) -> Optional[str]:
        """Persist session state to file."""
        ensure_dir = lambda d: os.makedirs(d, exist_ok=True) if d else None
        ensure_dir(self.config.auto_save_dir)
        ensure_dir(SESSIONS_DIR)
        session_id = self.session_id or "session"
        try:
            save_session(session_id, self.message_history, self.token_input, self.token_output)
            return os.path.join(SESSIONS_DIR, f"{session_id}.json")
        except Exception as e:
            print(f"Error persisting session: {e}")
        return None

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        return len(text.split()) * 4

    def render_summary(self) -> str:
        """Render usage summary report."""
        token_total = self.token_input + self.token_output
        lines = [
            "=== CodeAgent Session Summary ===",
            f"Session ID: {self.session_id or 'N/A'}",
            f"Turn count: {self.turn_count}",
            f"Message count: {len(self.message_history)}",
            f"Input tokens: {self.token_input}",
            f"Output tokens: {self.token_output}",
            f"Total tokens: {token_total}",
            f"Status: {'terminated' if self.is_terminated else 'active'}",
            f"Last turn: {datetime.now().isoformat()}"
        ]
        return "\n".join(lines)

    def reset(self):
        """Reset the engine to initial state."""
        self.turn_count = 0
        self.is_terminated = False
        self.message_history = []
        self.turn_results = []
        self.token_input = 0
        self.token_output = 0