"""A2A JSON-RPC 处理器 — 包装既有 ``run_chat_turn``。

零侵入设计：本模块不修改任何 WebUI 逻辑，只把 A2A 语义
（Message / Task / contextId）翻译成内部调用（session_id / user_msg），
再把结果包装回 A2A Task 对象。

支持方法：
- ``message/send``  发送消息（创建或续接 Task）→ 返回 Task
- ``tasks/get``     查询 Task 状态（从 session 历史重建）
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from .agent_card import build_agent_card
from .models import (
    STATE_COMPLETED,
    STATE_FAILED,
    Artifact,
    Message,
    Part,
    Task,
    TaskStatus,
    new_id,
)

logger = logging.getLogger(__name__)

# JSON-RPC 标准错误码
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603


# ── 发现端点 ───────────────────────────────────────────────────
async def a2a_agent_card(_: Request) -> JSONResponse:
    """GET /.well-known/agent-card.json — A2A Agent Card（公开发现）。"""
    return JSONResponse(build_agent_card())


# ── JSON-RPC 入口 ──────────────────────────────────────────────
async def a2a_jsonrpc(request: Request):
    """POST /a2a — A2A JSON-RPC 2.0 入口。

    ``message/stream`` 返回 SSE 流（StreamingResponse），其余返回 JSON。
    """
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(None, ERR_PARSE, "Parse error: invalid JSON")

    if not isinstance(body, dict):
        return _rpc_error(None, ERR_INVALID_REQUEST, "Invalid Request: body must be object")

    req_id = body.get("id")
    method = str(body.get("method") or "")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        return _rpc_error(req_id, ERR_INVALID_PARAMS, "Invalid params: must be object")

    # 流式方法单独处理（返回 SSE，不走 JSON-RPC 包装）
    if method == "message/stream":
        from .streaming import stream_response

        return await stream_response(params)

    try:
        if method == "message/send":
            result = await _handle_message_send(params)
        elif method == "tasks/get":
            result = await _handle_tasks_get(params)
        else:
            return _rpc_error(req_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
    except _A2AError as e:
        return _rpc_error(req_id, e.code, e.message)
    except Exception as e:  # noqa: BLE001
        logger.exception("a2a jsonrpc failed: %s", method)
        return _rpc_error(req_id, ERR_INTERNAL, f"Internal error: {e}")

    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


# ── message/send ───────────────────────────────────────────────
async def _handle_message_send(params: dict[str, Any]) -> dict[str, Any]:
    """处理 message/send：A2A Message → run_chat_turn → A2A Task。"""
    raw_msg = params.get("message")
    if not isinstance(raw_msg, dict):
        raise _A2AError(ERR_INVALID_PARAMS, "params.message is required")

    msg = Message.from_dict(raw_msg)
    text = msg.text().strip()
    if not text:
        raise _A2AError(ERR_INVALID_PARAMS, "message has no text part")

    cfg = params.get("configuration") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    # contextId 是 A2A 的对话分组标识；映射为内部 session_id（加前缀隔离）
    context_id = msg.context_id or new_id("ctx")
    session_id = f"a2a-{context_id}"
    task_id = msg.task_id or new_id("task")

    from codeagent.server.chat_turn import run_chat_turn

    max_rounds = cfg.get("maxToolRounds")
    try:
        max_rounds = int(max_rounds) if max_rounds is not None else None
    except (TypeError, ValueError):
        max_rounds = None

    try:
        result = await run_chat_turn(
            agent_id=str(cfg.get("agentId") or "default"),
            session_id=session_id,
            user_msg={"role": "user", "content": text},
            project_id=str(cfg.get("projectId") or ""),
            max_tool_rounds=max_rounds,
            channel="A2A",
            source="a2a",
            emit_ws=False,
            refresh_title=False,
            log_diary=False,
            with_evidence=True,
        )
        state = STATE_COMPLETED
        reply = str(result.get("reply") or "")
    except Exception as e:  # noqa: BLE001
        logger.exception("a2a message/send failed")
        state = STATE_FAILED
        reply = f"执行失败：{e}"
        result = {}

    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=state, message="" if state == STATE_COMPLETED else reply),
        artifacts=[
            Artifact(
                artifact_id=new_id("artifact"),
                name="reply",
                description="Agent 回复原文",
                parts=[Part(kind="text", text=reply)],
            )
        ],
        metadata={
            "sessionId": session_id,
            "toolsUsed": result.get("tools_used", []),
            "tokenUsage": result.get("token_usage", {}),
            "cost": result.get("cost", {}),
            "model": result.get("model", ""),
        },
    )
    return task.to_dict()


# ── tasks/get ──────────────────────────────────────────────────
async def _handle_tasks_get(params: dict[str, Any]) -> dict[str, Any]:
    """查询 Task：从磁盘 session 历史重建（无独立 Task 存储，保持零侵入）。

    注意：不能只查内存 SESSIONS —— 服务重启后内存缓存清空，
    必须从磁盘加载会话（load_or_create_chat_session）。
    """
    context_id = str(params.get("contextId") or "").strip()
    task_id = str(params.get("id") or "").strip()
    if not context_id:
        raise _A2AError(ERR_INVALID_PARAMS, "params.contextId is required")

    session_id = f"a2a-{context_id}"
    from seed.core.llm_sess import load_chat_session_from_disk

    sess = load_chat_session_from_disk(session_id, agent_id="default")
    if sess is None:
        raise _A2AError(ERR_INVALID_PARAMS, f"context not found: {context_id}")

    messages = getattr(sess, "messages", None) or []
    last_agent = ""
    for m in reversed(messages):
        if m.get("role") == "assistant":
            last_agent = str(m.get("content") or "")
            break

    task = Task(
        id=task_id or f"task-{context_id}",
        context_id=context_id,
        status=TaskStatus(state=STATE_COMPLETED),
        artifacts=[
            Artifact(
                artifact_id=new_id("artifact"),
                name="reply",
                parts=[Part(kind="text", text=last_agent)],
            )
        ],
        metadata={"sessionId": session_id, "messageCount": len(messages)},
    )
    return task.to_dict()


# ── 辅助 ───────────────────────────────────────────────────────
class _A2AError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _rpc_error(req_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    )
