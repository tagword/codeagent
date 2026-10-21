"""Bridge ``LLMWorker`` into seed's ``AgentRegistry`` so chat team tools work.

Background
----------
``seed_tools/team.py`` exposes ``call_agent`` / ``dispatch`` / ``parallel`` to the
LLM. Those tools look up targets via ``seed.core.agent_registry.AgentRegistry``
and call ``handle.run_task(task) -> str``.

The registry ships empty: nothing in the host ever constructs an
``AutonomousAgent`` (which needs ``session`` + ``turn_loop`` + ``llm_executor``)
and registers it. As a result the chat team tools always answered
``"Agent '<id>' not found in registry"``.

This module closes that gap with the *lightest* viable adapter: ``LLMWorker``
already runs a fully isolated per-agent turn (own agent_id, tools, system
prompt, session, memory), so we wrap it in an ``AgentHandle``-compatible object
instead of assembling an ``AutonomousAgent``.

Usage::

    from codeagent.runtime.agent_handle import LLMWorkerHandle
    from seed.core.agent_registry import AgentHandle, AgentRegistry

    AgentRegistry.register("default", AgentHandle(agent=LLMWorkerHandle("default")))
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMWorkerHandle:
    """``AgentHandle``-compatible wrapper around a per-agent ``LLMWorker``.

    ``AgentHandle._run_same_process`` calls ``self._agent.run_task(task)`` and
    reads ``result["content"]`` / ``result["error"]``. We expose exactly that
    contract, backed by ``LLMWorker.run``.

    Attributes:
        agent_id: Agent identity (persona / tools / memory scope).
        project_id: Optional project scope for the worker's tool resolution.
        max_tool_rounds: Tool-loop budget per delegated task.
        session_prefix: Session id prefix; each call gets its own session so
            delegated tasks do not pollute the caller's conversation.
    """

    agent_id: str = "default"
    project_id: str = ""
    max_tool_rounds: int = 12
    session_prefix: str = "delegate"
    _call_seq: int = field(default=0, init=False, repr=False)
    _worker: Any = field(default=None, init=False, repr=False)

    def run_task(self, task: str) -> dict[str, Any]:
        """Run ``task`` on this agent and return an ``AutonomousAgent``-shaped dict.

        Returns:
            ``{"content": str, "success": bool}`` on success, or
            ``{"content": "", "success": False, "error": str}`` on failure.
        """
        if not task or not str(task).strip():
            return {"content": "", "success": False, "error": "empty task"}

        # Import lazily: keeps module import cheap and avoids cycles at boot.
        from codeagent.runtime.llm_worker import LLMWorker

        worker = self._worker or LLMWorker(
            agent_id=self.agent_id, project_id=self.project_id
        )
        self._call_seq += 1
        session_id = f"{self.session_prefix}-{self.agent_id}-{self._call_seq}"

        def _invoke() -> tuple[str, dict[str, Any]]:
            return worker.run(
                session_id=session_id,
                user_text=str(task),
                max_tool_rounds=self.max_tool_rounds,
            )

        try:
            # LLMWorker.run() calls asyncio.run() internally, which explodes if we
            # are already inside a running loop (the normal case: chat team tools
            # are async). Detect that and offload to a worker thread so the nested
            # loop gets a clean thread-local event loop.
            try:
                asyncio.get_running_loop()
                in_loop = True
            except RuntimeError:
                in_loop = False

            if in_loop:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    reply, meta = pool.submit(_invoke).result()
            else:
                reply, meta = _invoke()
        except Exception as e:  # noqa: BLE001 — surface any failure as tool error
            logger.exception("LLMWorkerHandle.run_task failed for %s", self.agent_id)
            return {"content": "", "success": False, "error": str(e)}

        err = (meta or {}).get("error")
        if err:
            return {"content": reply or "", "success": False, "error": str(err)}
        return {"content": reply or "", "success": True}
