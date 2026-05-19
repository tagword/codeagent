"""Orchestrator sequential mode."""

from __future__ import annotations

from dataclasses import dataclass

import importlib.util
import sys
from pathlib import Path

# Import orchestrator without loading runtime/__init__ (avoids seed_tools in unit test).
_rt = Path(__file__).resolve().parents[1] / "codeagent" / "runtime"
for mod, rel in (
    ("codeagent.runtime.task_split", "task_split.py"),
    ("codeagent.runtime.worker", "worker.py"),
    ("codeagent.runtime.orchestrator", "orchestrator.py"),
):
    if mod not in sys.modules:
        spec = importlib.util.spec_from_file_location(mod, _rt / rel)
        assert spec and spec.loader
        m = importlib.util.module_from_spec(spec)
        sys.modules[mod] = m
        spec.loader.exec_module(m)

from codeagent.runtime.orchestrator import Orchestrator
from codeagent.runtime.worker import Worker


@dataclass
class _StubWorker:
    label: str
    calls: list[str]

    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        tools=None,
        max_tool_rounds: int = 16,
    ) -> tuple[str, dict]:
        self.calls.append(user_text)
        return f"{self.label}:{user_text}", {"session_id": session_id}


def test_orchestrator_sequential_subtasks() -> None:
    w1 = _StubWorker("A", [])
    w2 = _StubWorker("B", [])
    orch = Orchestrator(workers=[Worker(impl=w1), Worker(impl=w2)], parallel=False)
    reply, meta = orch.run(
        session_id="s1",
        user_text="ignored",
        metadata={"subtasks": ["task one", "task two"], "parallel": False},
    )
    assert "Subtask 1" in reply
    assert "A:task one" in reply
    assert "B:task two" in reply
    assert meta["orchestrator"]["mode"] == "sequential"
