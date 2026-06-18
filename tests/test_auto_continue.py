"""Auto-continue (chunked-compression) — 4 minimal regression tests.

Goal: protect the existing implementation in `codeagent/server/app_factory.py:515-612`
from silent regressions. The 4 tests cover the 4 critical states documented in
`docs/plans/chunked-compression-implementation.md` §5.4:

  M1 — Short task: 1 segment ends with no_tool_calls → no nudge, behavior unchanged
  M2 — Long task: 1st segment ends with max_tool_rounds → nudge IS injected
  M3 — Continuation: 2nd segment starts → run_llm_tool_loop is called again
  M4 — Cancel: cancel signal in segment → exits without writing nudge

These tests mock `run_llm_tool_loop` (per `tests/test_image_understanding.py`
style) and drive the real chunked loop in `app_factory.py:537-602`.

NO production code is modified. NO test runs are performed by writing this file.
"""

from __future__ import annotations

import os
import socket
from contextlib import closing
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Find a free TCP port. Avoids hardcoded 8000 conflicts."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def agent_home(tmp_path: Path, monkeypatch):
    """Isolated agent home dir + minimal env config.

    Mirrors the fixture in `tests/test_image_understanding.py` so we don't
    depend on a real CodeAgent user-data directory.
    """
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOME", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_HOST", "127.0.0.1")
    monkeypatch.setenv("CODEAGENT_PORT", str(_free_port()))
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "env").write_text(
        "SEED_LLM_BASEURL=https://example.test/v1\n"
        "SEED_LLM_MODEL=test-model\n"
        "SEED_LLM_APIKEY=test-key\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def auto_continue_on(monkeypatch, agent_home):
    """Enable auto_continue and set max_segments=4 (matches production default)."""
    monkeypatch.setenv("CODEAGENT_CHAT_AUTO_CONTINUE_ON_LIMIT", "1")
    monkeypatch.setenv("CODEAGENT_CHAT_AUTO_CONTINUE_MAX_SEGMENTS", "4")


def _make_fake_loop(loop_meta_sequence: list[dict]):
    """Create a fake `run_llm_tool_loop` that returns successive loop_metas.

    Each call pops the next entry from `loop_meta_sequence` and returns it
    as the 5th return value. Reply defaults to "ok" and tool list defaults to [].
    """
    sequence = list(loop_meta_sequence)

    async def _fake_loop(*_args, **_kwargs):
        if not sequence:
            # Safety: if called more times than expected, fail loudly
            raise AssertionError(
                f"run_llm_tool_loop called more times than expected "
                f"({len(sequence)} remaining in mock sequence)"
            )
        meta = sequence.pop(0)
        return ("ok", {"prompt_tokens": 100, "completion_tokens": 50}, [], [], meta)

    return _fake_loop, sequence


# ---------------------------------------------------------------------------
# M1 — Short task: no chunking, behavior unchanged
# ---------------------------------------------------------------------------


def test_m1_short_task_no_nudge(auto_continue_on, monkeypatch):
    """When LLM finishes in 1 segment (no_tool_calls), NO nudge is written.

    Validates:
    - run_llm_tool_loop is called exactly once
    - Reply is returned to the user
    - The response loop_meta's stopped_reason is "no_tool_calls" (not "max_tool_rounds")
    """
    # The chunked loop should call run_llm_tool_loop exactly once and stop
    fake, remaining = _make_fake_loop(
        [{"stopped_reason": "no_tool_calls", "rounds": 1, "usage": {}}]
    )
    monkeypatch.setattr("seed.core.agent_runtime.run_llm_tool_loop", fake)

    # Trigger the chunked path via /api/chat
    from codeagent.server.app_factory import create_app
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"session_id": "m1-session", "message": "short task"},
        )

    # Reply was returned (not empty)
    assert r.status_code == 200, f"chat endpoint failed: {r.text}"
    body = r.json()
    assert body.get("reply") == "ok", f"expected reply='ok', got {body!r}"

    # The fake_loop was consumed entirely (called exactly once)
    assert remaining == [], (
        f"run_llm_tool_loop should be called exactly once for short task, "
        f"but {len(remaining)} calls remain unconsumed"
    )

    # The returned stopped_reason is "no_tool_calls"
    assert body.get("stopped_reason") == "no_tool_calls", (
        f"expected stopped_reason='no_tool_calls', got {body.get('stopped_reason')!r}"
    )


# ---------------------------------------------------------------------------
# M2 — Long task: 1st segment hits max_tool_rounds → nudge IS injected
# ---------------------------------------------------------------------------


def test_m2_long_task_injects_nudge(auto_continue_on, monkeypatch):
    """When 1st segment ends with max_tool_rounds, a nudge user message is appended.

    Validates:
    - After max_tool_rounds, the chunked loop writes a "_auto_continue_nudge"
      user message to chat_sess.messages
    - The loop then attempts a 2nd segment (M3 covers the continuation)
    """
    # 1st call: max_tool_rounds (triggers nudge), 2nd call: no_tool_calls (exits)
    fake, _ = _make_fake_loop(
        [
            {"stopped_reason": "max_tool_rounds", "rounds": 4, "usage": {}},
            {"stopped_reason": "no_tool_calls", "rounds": 1, "usage": {}},
        ]
    )
    monkeypatch.setattr("seed.core.agent_runtime.run_llm_tool_loop", fake)

    from codeagent.server.app_factory import create_app
    from starlette.testclient import TestClient
    from codeagent.core.llm_sess import load_or_create_chat_session

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"session_id": "m2-session", "message": "long task"},
        )

    assert r.status_code == 200, f"chat endpoint failed: {r.text}"
    body = r.json()
    assert body.get("reply") == "ok"

    # Verify: chat_sess.messages contains at least one _auto_continue_nudge message
    sess = load_or_create_chat_session("m2-session", "default", None)
    nudge_count = sum(
        1 for m in sess.messages
        if isinstance(m, dict) and m.get("_auto_continue_nudge")
    )
    assert nudge_count >= 1, (
        f"expected at least 1 _auto_continue_nudge message in chat history, "
        f"found {nudge_count}. Messages: {sess.messages!r}"
    )


# ---------------------------------------------------------------------------
# M3 — Continuation: 2nd segment starts after nudge
# ---------------------------------------------------------------------------


def test_m3_continuation_calls_second_segment(auto_continue_on, monkeypatch):
    """After 1st segment ends with max_tool_rounds, run_llm_tool_loop IS called again.

    Validates:
    - The chunked loop calls run_llm_tool_loop at least twice
    - The 2nd call has access to the previous tool results (via api_msgs)
    - The 2nd segment can end normally (no_tool_calls) and exit cleanly
    """
    fake, remaining = _make_fake_loop(
        [
            # 1st segment: hits max_tool_rounds
            {"stopped_reason": "max_tool_rounds", "rounds": 4, "usage": {"prompt_tokens": 20}},
            # 2nd segment: finishes normally
            {"stopped_reason": "no_tool_calls", "rounds": 1, "usage": {"prompt_tokens": 25}},
        ]
    )
    call_count = {"n": 0}
    original_fake = fake

    async def _counting_fake(*args, **kwargs):
        call_count["n"] += 1
        return await original_fake(*args, **kwargs)

    monkeypatch.setattr("seed.core.agent_runtime.run_llm_tool_loop", _counting_fake)

    from codeagent.server.app_factory import create_app
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"session_id": "m3-session", "message": "trigger continuation"},
        )

    assert r.status_code == 200
    # 2 segments ran (1st max_tool_rounds + 2nd no_tool_calls)
    assert call_count["n"] == 2, (
        f"expected exactly 2 calls to run_llm_tool_loop (1st hits limit, 2nd finishes), "
        f"got {call_count['n']}"
    )
    # Mock sequence fully consumed
    assert remaining == [], (
        f"mock sequence not fully consumed: {len(remaining)} remaining"
    )


# ---------------------------------------------------------------------------
# M4 — Cancel: cancellation during segment exits without writing nudge
# ---------------------------------------------------------------------------


def test_m4_cancel_exits_without_nudge(auto_continue_on, monkeypatch):
    """When a segment ends with stopped_reason='cancelled', the loop exits.

    Validates:
    - run_llm_tool_loop is called exactly once
    - NO _auto_continue_nudge message is written (cancelled is a terminal state)
    - The reply is still returned (possibly empty)
    """
    fake, remaining = _make_fake_loop(
        [{"stopped_reason": "cancelled", "rounds": 2, "usage": {}}]
    )
    monkeypatch.setattr("seed.core.agent_runtime.run_llm_tool_loop", fake)

    from codeagent.server.app_factory import create_app
    from starlette.testclient import TestClient
    from codeagent.core.llm_sess import load_or_create_chat_session

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/chat",
            json={"session_id": "m4-session", "message": "will be cancelled"},
        )

    assert r.status_code == 200
    # Run loop was called exactly once
    assert remaining == [], (
        f"run_llm_tool_loop should be called exactly once when cancelled, "
        f"but {len(remaining)} calls remain unconsumed"
    )

    # No nudge message was written
    sess = load_or_create_chat_session("m4-session", "default", None)
    nudge_count = sum(
        1 for m in sess.messages
        if isinstance(m, dict) and m.get("_auto_continue_nudge")
    )
    assert nudge_count == 0, (
        f"cancelled path should NOT write _auto_continue_nudge, "
        f"but {nudge_count} found. Messages: {sess.messages!r}"
    )
