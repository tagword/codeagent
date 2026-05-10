"""Worker abstraction (v0 skeleton for multi-agent)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class WorkerProtocol(Protocol):
    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        tools: list[dict[str, Any]] | None = None,
        max_tool_rounds: int = 16,
    ) -> tuple[str, dict[str, Any]]:
        """Run a single user turn, returning assistant text + metadata."""


@dataclass
class Worker:
    """
    Minimal worker wrapper.

    Phase 1: delegates to the existing single-agent runtime (HTTP API uses seed.server).
    Phase 2+: will host an isolated tool-loop with its own tool registry, memory view, etc.
    """

    impl: WorkerProtocol | None = None

    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        tools: list[dict[str, Any]] | None = None,
        max_tool_rounds: int = 16,
    ) -> tuple[str, dict[str, Any]]:
        if self.impl is None:
            raise RuntimeError("Worker.impl is not configured")
        return self.impl.run(
            session_id=session_id,
            user_text=user_text,
            tools=tools,
            max_tool_rounds=max_tool_rounds,
        )

