"""A2A 客户端 — 让本 Agent 作为标准 A2A Client 调用外部 Agent。

为什么需要它
------------
此前与外部 agent 通信靠「手撸脚本直接 POST /a2a」：跳过发现、硬编码 URL、
假设对方支持 JSONRPC 与流式。对方一换地址/传输/认证方式，脚本立刻失效。

A2A 是双向对等协议。服务端（``handlers``/``streaming``）解决「被调用」，
本模块解决「主动调用」，两者合起来才是完整实现。

标准流程（规范 8.2 / 8.3.2）
----------------------------
1. **发现**：GET ``/.well-known/agent-card.json`` 拿名片
2. **协商**：读 ``supportedInterfaces``，选第一个自己支持的传输
3. **调用**：按名片声明的 URL / 认证方式 / 流式能力发请求

本客户端强制走完 1→2，**不允许跳过发现直接调用**——这是与手撸脚本的本质区别。

用法::

    async with A2AClient.discover("http://127.0.0.1:18898") as client:
        task = await client.send("把 X 改成 Y", project_id="proj-1")
        print(task.text())

    # 流式
    async for ev in client.stream("写个脚本"):
        if ev.kind == "artifact":
            print(ev.text, end="")
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from .client_card import AgentCard
from .models import (
    STATE_CANCELED,
    STATE_COMPLETED,
    STATE_FAILED,
    TERMINAL_STATES,
    Message,
    Part,
    Task,
    new_id,
)

logger = logging.getLogger(__name__)

WELL_KNOWN_PATH = "/.well-known/agent-card.json"

# JSON-RPC 标准错误码 → 可读文案
_RPC_ERRORS = {
    -32700: "解析错误：请求不是合法 JSON",
    -32600: "非法请求",
    -32601: "方法不存在（对方可能不支持该操作）",
    -32602: "参数非法",
    -32603: "对方内部错误",
}


class A2AError(Exception):
    """A2A 调用失败（网络 / 协议 / 业务错误统一入口）。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class StreamEvent:
    """流式事件（把 SSE 的 status / artifact 归一成一种结构）。"""

    kind: str  # status | artifact | error
    state: str = ""
    text: str = ""
    final: bool = False
    # 协议语义：append=True 表示增量片段，False 表示全量快照（覆盖已累积内容）
    append: bool = False
    task_id: str = ""
    context_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class A2AClient:
    """标准 A2A 客户端。

    构造后所有调用都基于**名片协商出的接口**，不硬编码 URL。
    """

    def __init__(
        self,
        card: AgentCard,
        *,
        token: str = "",
        timeout: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.card = card
        self._iface = card.select_interface()  # 规范 8.3.2：协商失败即报错
        self._token = token
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    # ── 发现 ───────────────────────────────────────────────────
    @classmethod
    async def discover(
        cls,
        base_url: str,
        *,
        token: str = "",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> A2AClient:
        """规范 8.2 Well-Known URI 发现：拉名片并构造客户端。"""
        url = base_url.rstrip("/") + WELL_KNOWN_PATH
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=transport, follow_redirects=True
            ) as http:
                resp = await http.get(url, headers=headers)
        except httpx.HTTPError as e:
            raise A2AError(f"发现失败：无法访问 {url}（{e}）") from e

        if resp.status_code != 200:
            raise A2AError(
                f"发现失败：{url} 返回 HTTP {resp.status_code}",
                code=resp.status_code,
            )
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise A2AError(f"发现失败：{url} 返回的不是合法 JSON") from e
        if not isinstance(data, dict):
            raise A2AError(f"发现失败：{url} 返回的 Agent Card 不是对象")

        return cls(data and AgentCard.from_dict(data), token=token, timeout=timeout, transport=transport)

    # ── 生命周期 ───────────────────────────────────────────────
    async def __aenter__(self) -> A2AClient:
        self._client = httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport, follow_redirects=True
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def close(self) -> None:
        await self.__aexit__(None, None, None)

    # ── 调用 ───────────────────────────────────────────────────
    async def send(
        self,
        text: str,
        *,
        context_id: str = "",
        task_id: str = "",
        project_id: str = "",
        max_tool_rounds: int | None = None,
    ) -> Task:
        """``message/send`` — 同步执行，返回终态 Task。"""
        params = self._build_params(
            text,
            context_id=context_id,
            task_id=task_id,
            project_id=project_id,
            max_tool_rounds=max_tool_rounds,
        )
        result = await self._rpc("message/send", params)
        if not isinstance(result, dict):
            raise A2AError("message/send 返回结果不是对象")
        return Task.from_dict(result)

    async def stream(
        self,
        text: str,
        *,
        context_id: str = "",
        task_id: str = "",
        project_id: str = "",
        max_tool_rounds: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """``message/stream`` — SSE 流式执行。

        名片声明 ``capabilities.streaming=false`` 时直接报错，
        不静默降级——降级会让调用方以为拿到了流。
        """
        if not self.card.supports_streaming:
            raise A2AError(
                f"agent '{self.card.name}' 未声明 streaming 能力，请改用 send()"
            )
        params = self._build_params(
            text,
            context_id=context_id,
            task_id=task_id,
            project_id=project_id,
            max_tool_rounds=max_tool_rounds,
        )
        body = {"jsonrpc": "2.0", "id": new_id("req"), "method": "message/stream", "params": params}

        client = self._ensure_client()
        try:
            async with client.stream(
                "POST", self._iface.url, json=body, headers=self._headers()
            ) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                    raise A2AError(
                        f"message/stream 返回 HTTP {resp.status_code}: {detail}",
                        code=resp.status_code,
                    )
                async for ev in _iter_sse(resp):
                    yield ev
        except httpx.HTTPError as e:
            raise A2AError(f"message/stream 网络错误：{e}") from e

    async def get_task(self, *, task_id: str = "", context_id: str = "") -> Task:
        """``tasks/get`` — 查询任务状态。"""
        if not task_id and not context_id:
            raise A2AError("get_task 需要 task_id 或 context_id")
        params: dict[str, Any] = {}
        if task_id:
            params["id"] = task_id
        if context_id:
            params["contextId"] = context_id
        result = await self._rpc("tasks/get", params)
        if not isinstance(result, dict):
            raise A2AError("tasks/get 返回结果不是对象")
        return Task.from_dict(result)

    async def cancel(self, task_id: str) -> Task:
        """``tasks/cancel`` — 取消任务。"""
        result = await self._rpc("tasks/cancel", {"id": task_id})
        if not isinstance(result, dict):
            raise A2AError("tasks/cancel 返回结果不是对象")
        return Task.from_dict(result)

    async def wait(
        self,
        task: Task,
        *,
        poll_interval: float = 2.0,
        max_wait: float = 600.0,
    ) -> Task:
        """轮询直到 Task 进入终态（对方不支持推送通知时的兜底）。"""
        import asyncio

        waited = 0.0
        current = task
        while current.status.state not in TERMINAL_STATES:
            if waited >= max_wait:
                raise A2AError(
                    f"等待任务超时（{max_wait}s），当前状态 {current.status.state}"
                )
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            current = await self.get_task(task_id=current.id, context_id=current.context_id)
        return current

    # ── 内部 ───────────────────────────────────────────────────
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # 未用 async with 时自动建连接，调用方无需强制上下文管理
            self._client = httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport, follow_redirects=True
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _build_params(
        self,
        text: str,
        *,
        context_id: str,
        task_id: str,
        project_id: str,
        max_tool_rounds: int | None,
    ) -> dict[str, Any]:
        msg = Message(
            role="user",
            parts=[Part(kind="text", text=text)],
            message_id=new_id("msg"),
            context_id=context_id,
            task_id=task_id,
            metadata={"projectId": project_id} if project_id else {},
        )
        params: dict[str, Any] = {"message": _message_to_dict(msg)}
        # 规范 8.3.2：接口声明了 tenant 就必须带上
        if self._iface.tenant:
            params["tenant"] = self._iface.tenant
        if max_tool_rounds is not None:
            params["configuration"] = {"maxToolRounds": max_tool_rounds}
        return params

    async def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        """发 JSON-RPC 请求并解包结果。"""
        client = self._ensure_client()
        body = {"jsonrpc": "2.0", "id": new_id("req"), "method": method, "params": params}
        try:
            resp = await client.post(self._iface.url, json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise A2AError(f"{method} 网络错误：{e}") from e

        if resp.status_code != 200:
            raise A2AError(
                f"{method} 返回 HTTP {resp.status_code}: {resp.text[:300]}",
                code=resp.status_code,
            )
        try:
            payload = resp.json()
        except json.JSONDecodeError as e:
            raise A2AError(f"{method} 返回的不是合法 JSON") from e

        if not isinstance(payload, dict):
            raise A2AError(f"{method} 返回的 JSON-RPC 响应不是对象")

        err = payload.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            msg = str(err.get("message") or "")
            hint = _RPC_ERRORS.get(code, "") if isinstance(code, int) else ""
            raise A2AError(
                f"{method} 失败：{hint or msg}" + (f"（{msg}）" if hint and msg else ""),
                code=code if isinstance(code, int) else None,
            )
        if "result" not in payload:
            raise A2AError(f"{method} 响应缺少 result 字段")
        return payload["result"]


def _message_to_dict(msg: Message) -> dict[str, Any]:
    """Message → A2A wire 格式（models.Message 只有 from_dict，这里补序列化）。"""
    out: dict[str, Any] = {
        "role": msg.role,
        "parts": [p.to_dict() for p in msg.parts],
        "messageId": msg.message_id,
    }
    if msg.context_id:
        out["contextId"] = msg.context_id
    if msg.task_id:
        out["taskId"] = msg.task_id
    if msg.metadata:
        out["metadata"] = msg.metadata
    return out


async def _iter_sse(resp: httpx.Response) -> AsyncIterator[StreamEvent]:
    """解析 A2A SSE 流（``event:`` / ``data:`` 帧）为 StreamEvent。"""
    event_name = ""
    async for line in resp.aiter_lines():
        line = line.rstrip("\r")
        if not line:
            event_name = ""
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("a2a client: 跳过非法 SSE data: %s", raw[:120])
            continue
        if not isinstance(data, dict):
            continue
        yield _to_event(event_name, data)


def _to_event(event_name: str, data: dict[str, Any]) -> StreamEvent:
    """把 A2A SSE 负载归一成 StreamEvent。"""
    kind = str(data.get("kind") or event_name or "")
    task_id = str(data.get("taskId") or "")
    context_id = str(data.get("contextId") or "")

    if kind == "status-update" or event_name == "status":
        status = data.get("status") if isinstance(data.get("status"), dict) else {}
        return StreamEvent(
            kind="status",
            state=str(status.get("state") or ""),
            final=bool(data.get("final")),
            task_id=task_id,
            context_id=context_id,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            raw=data,
        )

    if kind == "artifact-update" or event_name == "artifact":
        artifact = data.get("artifact") if isinstance(data.get("artifact"), dict) else {}
        text = "".join(
            str(p.get("text") or "")
            for p in (artifact.get("parts") or [])
            if isinstance(p, dict) and p.get("kind") == "text"
        )
        return StreamEvent(
            kind="artifact",
            text=text,
            final=bool(data.get("lastChunk")),
            append=bool(data.get("append", True)),
            task_id=task_id,
            context_id=context_id,
            raw=data,
        )

    if event_name == "error":
        return StreamEvent(
            kind="error",
            text=str(data.get("message") or ""),
            final=True,
            raw=data,
        )

    return StreamEvent(kind=kind or "unknown", task_id=task_id, context_id=context_id, raw=data)


def is_terminal(task: Task) -> bool:
    """Task 是否已进入终态。"""
    return task.status.state in TERMINAL_STATES


__all__ = [
    "A2AClient",
    "A2AError",
    "StreamEvent",
    "is_terminal",
    "STATE_CANCELED",
    "STATE_COMPLETED",
    "STATE_FAILED",
]
