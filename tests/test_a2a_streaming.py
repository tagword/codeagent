"""A2A 流式（message/stream, SSE）测试。

覆盖：
1. _EventBridge 事件翻译（text_delta → delta、run_finished → 哨兵）
2. SSE 帧格式
3. stream_message 端到端（fake run_chat_turn 触发 broadcast_fn）
4. 空文本 / 异常路径
"""
import asyncio
import json

import pytest

from codeagent.server.a2a import streaming as st


# ---------- SSE 帧格式 ----------
def test_sse_frame_format():
    raw = st._sse("status", {"state": "working"})
    text = raw.decode()
    assert text.startswith("event: status\n")
    assert "data: " in text
    assert text.endswith("\n\n")
    payload = json.loads(text.split("data: ", 1)[1].strip())
    assert payload["state"] == "working"


# ---------- EventBridge ----------
@pytest.mark.asyncio
async def test_bridge_translates_delta():
    bridge = st._EventBridge(asyncio.get_running_loop())
    await bridge("a", "s", {"type": "text_delta", "text": "hello"})
    item = bridge.queue.get_nowait()
    assert item == {"kind": "delta", "text": "hello"}


@pytest.mark.asyncio
async def test_bridge_captures_final_text_and_tools():
    bridge = st._EventBridge(asyncio.get_running_loop())
    await bridge("a", "s", {"type": "text_done", "text": "final", "tools_used": ["file_read"]})
    assert bridge.final_text == "final"
    assert bridge.tools_used == ["file_read"]


@pytest.mark.asyncio
async def test_bridge_run_finished_sentinel():
    bridge = st._EventBridge(asyncio.get_running_loop())
    await bridge("a", "s", {"type": "run_finished"})
    assert bridge.finished is True
    assert bridge.queue.get_nowait() is None


@pytest.mark.asyncio
async def test_bridge_ignores_unknown_events():
    bridge = st._EventBridge(asyncio.get_running_loop())
    await bridge("a", "s", {"type": "context_usage", "x": 1})
    assert bridge.queue.empty()


# ---------- stream_message 端到端 ----------
async def _collect(params):
    return [chunk async for chunk in st.stream_message(params)]


def _parse_events(chunks):
    """把 SSE 字节流解析成 [(event, data), ...]。"""
    out = []
    for c in chunks:
        text = c.decode()
        lines = text.strip().split("\n")
        ev = lines[0].split(": ", 1)[1]
        data = json.loads(lines[1].split(": ", 1)[1])
        out.append((ev, data))
    return out


@pytest.mark.asyncio
async def test_stream_happy_path(monkeypatch):
    """fake run_chat_turn 触发 broadcast_fn，验证 SSE 事件序列。"""
    async def _fake(**kwargs):
        bf = kwargs["broadcast_fn"]
        await bf("default", kwargs["session_id"], {"type": "run_started"})
        await bf("default", kwargs["session_id"], {"type": "text_delta", "text": "你好"})
        await bf("default", kwargs["session_id"], {"type": "text_delta", "text": "世界"})
        await bf("default", kwargs["session_id"], {
            "type": "text_done", "text": "你好世界", "tools_used": ["bash"],
        })
        await bf("default", kwargs["session_id"], {"type": "run_finished"})
        return {"reply": "你好世界", "tools_used": ["bash"], "token_usage": {"total_tokens": 5}}

    import codeagent.server.chat_turn as ct
    monkeypatch.setattr(ct, "run_chat_turn", _fake)

    chunks = await _collect({
        "message": {"role": "user", "contextId": "ctx-s1", "parts": [{"text": "hi"}]},
    })
    events = _parse_events(chunks)

    kinds = [e for e, _ in events]
    assert kinds[0] == "status"
    assert events[0][1]["status"]["state"] == "working"
    # 有 delta 增量
    deltas = [d for e, d in events if e == "artifact" and d.get("append")]
    assert len(deltas) == 2
    assert deltas[0]["artifact"]["parts"][0]["text"] == "你好"
    # 终态 completed
    final = events[-1][1]
    assert final["status"]["state"] == "completed"
    assert final["final"] is True
    assert final["metadata"]["toolsUsed"] == ["bash"]


@pytest.mark.asyncio
async def test_stream_empty_text():
    chunks = await _collect({"message": {"role": "user", "parts": []}})
    events = _parse_events(chunks)
    assert events[0][0] == "error"
    assert events[0][1]["code"] == -32602


@pytest.mark.asyncio
async def test_stream_failure_path(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("stream boom")

    import codeagent.server.chat_turn as ct
    monkeypatch.setattr(ct, "run_chat_turn", _boom)

    chunks = await _collect({
        "message": {"role": "user", "parts": [{"text": "x"}]},
    })
    events = _parse_events(chunks)
    assert events[-1][1]["status"]["state"] == "failed"
    assert "stream boom" in events[-1][1]["status"]["message"]


@pytest.mark.asyncio
async def test_stream_context_id_mapping(monkeypatch):
    """contextId → session_id 前缀映射。"""
    seen = {}

    async def _fake(**kwargs):
        seen["session_id"] = kwargs["session_id"]
        bf = kwargs["broadcast_fn"]
        await bf("default", kwargs["session_id"], {"type": "run_finished"})
        return {"reply": "ok"}

    import codeagent.server.chat_turn as ct
    monkeypatch.setattr(ct, "run_chat_turn", _fake)

    await _collect({
        "message": {"role": "user", "contextId": "ctx-map", "parts": [{"text": "x"}]},
    })
    assert seen["session_id"] == "a2a-ctx-map"
