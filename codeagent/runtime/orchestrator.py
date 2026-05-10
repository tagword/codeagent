"""Orchestrator abstraction (v0 skeleton for multi-agent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .worker import Worker


@dataclass
class Orchestrator:
    """
    Minimal orchestrator placeholder.

    Phase 2+: will split tasks and dispatch to multiple workers (parallel or staged),
    then merge results back into a single user-facing reply and shared session.
    """

    workers: list[Worker] = field(default_factory=list)

    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        max_tool_rounds: int = 16,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if not self.workers:
            raise RuntimeError("Orchestrator has no workers configured")
        # v0: just use the first worker (single-agent behavior).
        reply, meta = self.workers[0].run(
            session_id=session_id,
            user_text=user_text,
            max_tool_rounds=max_tool_rounds,
        )
        out_meta = dict(meta or {})
        if metadata:
            out_meta["orchestrator"] = metadata
        out_meta.setdefault("workers_used", 1)
        return reply, out_meta

