"""A2A 流式支持 — ``message/stream`` (SSE)。

A2A 规范定义三种交互：Request/Response、Streaming(SSE)、Push Notifications。
本模块实现 Streaming：把 ``run_chat_turn`` 的内部广播事件
（text_delta / text_done / run_finished）翻译成 A2A SSE 事件。

零侵入：复用 ``run_chat_turn`` 既有的 ``broadcast_fn`` 钩子，
不修改 chat_turn 一行代码。

SSE 事件形状（对齐 A2A 规范）：
- ``TaskStatusUpdateEvent``  任务状态变更（working/completed/failed）
- ``TaskArtifactUpdateEvent`` 产出增量（流式文本）
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from .context import ContextError, record_task
from .context import resolve as resolve_context
from .models import (
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_WORKING,
)

logger = logging.getLogger(__name__)


class _EventBridge:
    """把 run_chat_turn 的 broadcast_fn 回调桥接到 asyncio.Queue。

    broadcast_fn 从工作线程通过 run_coroutine_threadsafe 调用，
    因此本类的方法必须是 async 且线程安全地投递到队列。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.final_text = ""
        self.tools_used: list[str] = []
        self.finished = False

    async def __call__(self, _agent_id: str, _session_id: str, payload: dict[str, Any]) -> None:
        """broadcast_fn 签名：(agent_id, session_id, payload) -> None。"""
        etype = str(payload.get("type") or "")
        if etype == "text_delta":
            self.queue.put_nowait({"kind": "delta", "text": str(payload.get("text") or "")})
        elif etype in ("text_done", "reply"):
            self.final_text = str(payload.get("text") or self.final_text)
            tu = payload.get("tools_used")
            if isinstance(tu, list):
                self.tools_used = [str(x) for x in tu]
        elif etype == "run_finished":
            self.finished = True
            self.queue.put_nowait(None)  # 哨兵：结束
        elif etype in ("run_started", "message_queued"):
            self.queue.put_nowait({"kind": "status", "state": STATE_WORKING})


def _sse(event: str, data: dict[str, Any]) -> bytes:
    """构造 SSE 帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


async def stream_message(params: dict[str, Any]) -> AsyncIterator[bytes]:
    """执行 message/stream，产出 A2A SSE 事件流。

    产出序列：
    1. TaskStatusUpdateEvent(working)  — 任务开始
    2. TaskArtifactUpdateEvent(append) — 文本增量（多次）
    3. TaskStatusUpdateEvent(completed|failed) + 最终 artifact
    """
    from codeagent.server.chat_turn import run_chat_turn

    raw_msg = params.get("message") or {}
    if not isinstance(raw_msg, dict):
        yield _sse("error", {"code": -32602, "message": "params.message is required"})
        return

    from .models import Message

    msg = Message.from_dict(raw_msg)
    text = msg.text().strip()
    if not text:
        yield _sse("error", {"code": -32602, "message": "message has no text part"})
        return

    cfg = params.get("configuration") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    # 与 message/send 共用同一套上下文解析（含 taskId 反查）
    try:
        rctx = resolve_context(msg, cfg)
    except ContextError as e:
        yield _sse("error", {"code": -32602, "message": str(e)})
        return
    context_id = rctx.context_id
    session_id = rctx.session_id
    task_id = rctx.task_id

    loop = asyncio.get_running_loop()
    bridge = _EventBridge(loop)

    max_rounds = cfg.get("maxToolRounds")
    try:
        max_rounds = int(max_rounds) if max_rounds is not None else None
    except (TypeError, ValueError):
        max_rounds = None

    # 1. 任务开始
    yield _sse("status", {
        "kind": "status-update",
        "taskId": task_id,
        "contextId": context_id,
        "status": {"state": STATE_WORKING},
        "final": False,
    })

    # 2. 后台执行 run_chat_turn（emit_ws=True 才能触发 broadcast_fn）
    async def _run() -> dict[str, Any]:
        try:
            return await run_chat_turn(
                agent_id=str(cfg.get("agentId") or "default"),
                session_id=session_id,
                user_msg={"role": "user", "content": text},
                project_id=rctx.project_id,
                max_tool_rounds=max_rounds,
                channel="A2A",
                source="a2a",
                emit_ws=True,          # 关键：开启广播，才能拿到流式事件
                broadcast_fn=bridge,   # 桥接到队列
                refresh_title=False,
                log_diary=False,
                with_evidence=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("a2a stream run failed")
            return {"__error__": str(e)}

    run_task = asyncio.create_task(_run())

    # 3. 边跑边推增量
    #    注意：run_chat_turn 异常时不会触发 run_finished，队列会永久阻塞。
    #    因此用 wait 竞速：队列有事件就推，任务结束就退出。
    def _delta_event(text: str) -> bytes:
        return _sse("artifact", {
            "kind": "artifact-update",
            "taskId": task_id,
            "contextId": context_id,
            "artifact": {
                "artifactId": f"artifact-{task_id}",
                "name": "reply",
                "parts": [{"kind": "text", "text": text}],
            },
            "append": True,
            "lastChunk": False,
        })

    def _status_event(state: str) -> bytes:
        return _sse("status", {
            "kind": "status-update",
            "taskId": task_id,
            "contextId": context_id,
            "status": {"state": state},
            "final": False,
        })

    get_task: asyncio.Task | None = None
    try:
        while True:
            if get_task is None:
                get_task = asyncio.ensure_future(bridge.queue.get())
            done, _pending = await asyncio.wait(
                {get_task, run_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if get_task in done:
                item = get_task.result()
                get_task = None
                if item is None:
                    break
                if item["kind"] == "delta":
                    yield _delta_event(item["text"])
                elif item["kind"] == "status":
                    yield _status_event(item["state"])
            if run_task in done:
                # 任务已结束：排空队列剩余事件后退出
                if get_task is not None:
                    get_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await get_task
                    get_task = None
                while not bridge.queue.empty():
                    item = bridge.queue.get_nowait()
                    if item is None:
                        break
                    if item["kind"] == "delta":
                        yield _delta_event(item["text"])
                break
    except asyncio.CancelledError:
        run_task.cancel()
        raise

    result = await run_task
    err = result.get("__error__") if isinstance(result, dict) else None
    final_text = bridge.final_text or (result.get("reply") if isinstance(result, dict) else "") or ""

    # 登记 taskId → contextId 绑定，供后续只传 taskId 的调用反查
    record_task(
        session_id, task_id,
        agent_id=str(cfg.get("agentId") or "default"),
        project_id=rctx.project_id,
    )

    # 4. 终态
    if err:
        yield _sse("status", {
            "kind": "status-update",
            "taskId": task_id,
            "contextId": context_id,
            "status": {"state": STATE_FAILED, "message": err},
            "final": True,
        })
        return

    # 补齐最终 artifact（若增量未覆盖）
    if final_text:
        yield _sse("artifact", {
            "kind": "artifact-update",
            "taskId": task_id,
            "contextId": context_id,
            "artifact": {
                "artifactId": f"artifact-{task_id}",
                "name": "reply",
                "parts": [{"kind": "text", "text": final_text}],
            },
            "append": False,
            "lastChunk": True,
        })

    yield _sse("status", {
        "kind": "status-update",
        "taskId": task_id,
        "contextId": context_id,
        "status": {"state": STATE_COMPLETED},
        "final": True,
        "metadata": {
            "sessionId": session_id,
            "projectId": rctx.project_id,
            "inferredFromTask": rctx.inferred_from_task,
            "toolsUsed": bridge.tools_used or (result.get("tools_used") if isinstance(result, dict) else []) or [],
            "tokenUsage": (result.get("token_usage") if isinstance(result, dict) else {}) or {},
            "cost": (result.get("cost") if isinstance(result, dict) else {}) or {},
        },
    })


async def stream_response(params: dict[str, Any]):
    """Starlette StreamingResponse 适配（media_type=text/event-stream）。"""
    from starlette.responses import StreamingResponse

    return StreamingResponse(
        stream_message(params),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
