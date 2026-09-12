"""Tests for the AgentRegistry bridge (chat team tools enablement).

Covers:
* ``LLMWorkerHandle`` contract (``run_task`` → ``{"content", "success"}``)
* nested-event-loop handling (chat tools are async; LLMWorker.run uses asyncio.run)
* ``register_disk_agents`` idempotency / skip / overwrite semantics
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from codeagent.runtime.agent_bootstrap import register_disk_agents
from codeagent.runtime.agent_handle import LLMWorkerHandle
from seed.core.agent_registry import AgentHandle, AgentRegistry


@pytest.fixture(autouse=True)
def _clean_registry():
    AgentRegistry.clear()
    yield
    AgentRegistry.clear()


# ── LLMWorkerHandle ──────────────────────────────────────────────


def test_run_task_returns_content_and_success():
    h = LLMWorkerHandle(agent_id="default")
    with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
        mock_worker.return_value.run.return_value = ("hello", {"model": "m"})
        out = h.run_task("say hi")
    assert out == {"content": "hello", "success": True}


def test_run_task_empty_task_rejected():
    h = LLMWorkerHandle(agent_id="default")
    out = h.run_task("   ")
    assert out["success"] is False
    assert out["error"] == "empty task"


def test_run_task_surfaces_worker_error():
    h = LLMWorkerHandle(agent_id="default")
    with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
        mock_worker.return_value.run.return_value = ("partial", {"error": "boom"})
        out = h.run_task("do it")
    assert out["success"] is False
    assert out["error"] == "boom"
    assert out["content"] == "partial"


def test_run_task_catches_exception():
    h = LLMWorkerHandle(agent_id="default")
    with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
        mock_worker.return_value.run.side_effect = RuntimeError("kaboom")
        out = h.run_task("do it")
    assert out["success"] is False
    assert "kaboom" in out["error"]


def test_run_task_works_inside_running_loop():
    """The regression that broke chat team tools: asyncio.run() nested in a loop."""
    h = LLMWorkerHandle(agent_id="default")

    async def _inner():
        with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
            mock_worker.return_value.run.return_value = ("from-loop", {})
            return h.run_task("hi")

    out = asyncio.run(_inner())
    assert out == {"content": "from-loop", "success": True}


def test_run_task_distinct_sessions_per_call():
    h = LLMWorkerHandle(agent_id="default")
    seen = []

    def _fake_run(*, session_id, user_text, max_tool_rounds):
        seen.append(session_id)
        return ("ok", {})

    with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
        mock_worker.return_value.run.side_effect = _fake_run
        h.run_task("a")
        h.run_task("b")
    assert len(set(seen)) == 2, "each delegated call needs its own session"


# ── AgentHandle integration ──────────────────────────────────────


def test_agent_handle_wraps_worker_handle():
    """AgentHandle._run_same_process reads result['content'] / ['error']."""
    handle = AgentHandle(agent=LLMWorkerHandle(agent_id="default"))
    with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
        mock_worker.return_value.run.return_value = ("wrapped", {})
        assert handle.run_task("x") == "wrapped"


def test_agent_handle_reports_error_text():
    handle = AgentHandle(agent=LLMWorkerHandle(agent_id="default"))
    with patch("codeagent.runtime.llm_worker.LLMWorker") as mock_worker:
        mock_worker.return_value.run.side_effect = RuntimeError("nope")
        assert "Error" in handle.run_task("x")


# ── register_disk_agents ─────────────────────────────────────────


def test_register_disk_agents_registers_ids():
    out = register_disk_agents(agent_ids=["alpha", "beta"])
    assert out["registered"] == ["alpha", "beta"]
    assert set(AgentRegistry.list().keys()) == {"alpha", "beta"}


def test_register_disk_agents_idempotent():
    register_disk_agents(agent_ids=["alpha"])
    out = register_disk_agents(agent_ids=["alpha"])
    assert out["registered"] == []
    assert out["skipped"] == ["alpha"]


def test_register_disk_agents_overwrite():
    register_disk_agents(agent_ids=["alpha"])
    out = register_disk_agents(agent_ids=["alpha"], overwrite=True)
    assert out["registered"] == ["alpha"]


def test_register_disk_agents_skips_blank_ids():
    out = register_disk_agents(agent_ids=["", "beta"])
    assert out["registered"] == ["beta"]


def test_register_disk_agents_discovers_from_disk(tmp_path):
    """Discovery path: only dirs with persona/ qualify; testagent is skipped."""
    import codeagent.server.webui_handlers_agentmeta as meta

    agents_root = tmp_path / "agents"
    (agents_root / "good" / "persona").mkdir(parents=True)
    (agents_root / "nopersona").mkdir(parents=True)
    (agents_root / "testagent" / "persona").mkdir(parents=True)

    with patch.object(meta, "_agents_dir", return_value=agents_root):
        out = register_disk_agents()
    assert out["registered"] == ["good"]
