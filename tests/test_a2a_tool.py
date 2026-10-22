"""A2A 客户端工具层测试（seed_tools.a2a）。

重点覆盖：
- append 语义：增量拼接 vs 全量快照覆盖（回归：曾出现「流流式流式成功」重复）
- 参数校验与错误分支
- 工具注册
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest


# ── 假协议层 ────────────────────────────────────────────────
@dataclass
class _FakeCard:
    name: str = "fake-agent"
    description: str = "fake"
    protocol_version: str = "0.2.5"
    version: str = "1.0.0"
    supports_streaming: bool = True
    supports_push_notifications: bool = False
    skills: list = field(default_factory=list)

    def select_interface(self):
        @dataclass
        class _I:
            transport: str = "JSONRPC"
            url: str = "http://x/a2a"

        return _I()

    def requires_auth(self) -> bool:
        return False


@dataclass
class _FakeStatus:
    state: str = "completed"
    message: str = ""


@dataclass
class _FakeTask:
    id: str = "task-1"
    context_id: str = "ctx-1"
    status: _FakeStatus = field(default_factory=_FakeStatus)
    metadata: dict = field(default_factory=dict)
    _text: str = "ok"

    def text(self) -> str:
        return self._text


@dataclass
class _FakeEvent:
    kind: str
    text: str = ""
    state: str = ""
    append: bool = True
    metadata: dict = field(default_factory=dict)


class _FakeClient:
    """按脚本回放事件；记录调用参数。"""

    def __init__(self, events: list[_FakeEvent] | None = None):
        self.card = _FakeCard()
        self.events = events or []
        self.closed = False
        self.sent: list[tuple[str, dict]] = []

    @classmethod
    async def discover(cls, base_url: str, token: str = "", timeout: float = 60.0):
        return cls()

    async def send(self, message: str, **kwargs):
        self.sent.append((message, kwargs))
        return _FakeTask()

    async def stream(self, message: str, **kwargs):
        for ev in self.events:
            yield ev

    async def get_task(self, task_id: str = "", context_id: str = ""):
        return _FakeTask(id=task_id or "task-ctx", context_id=context_id or "ctx-1")

    async def cancel(self, task_id: str):
        return _FakeTask(id=task_id, status=_FakeStatus(state="canceled"))

    async def close(self):
        self.closed = True


class _FakeA2AError(Exception):
    pass


@pytest.fixture()
def patch_protocol(monkeypatch):
    """把工具层的延迟导入替换成假实现。"""
    import seed_tools.a2a as mod

    holder: dict[str, Any] = {"client": _FakeClient()}

    def _loader():
        return _FakeClient, _FakeA2AError

    monkeypatch.setattr(mod, "_load_protocol", _loader)

    async def _discover(base_url, token="", timeout=60.0):
        return holder["client"]

    monkeypatch.setattr(_FakeClient, "discover", classmethod(lambda cls, *a, **k: _discover(*a, **k)))
    return holder


def _run(coro):
    return asyncio.run(coro)


# ── append 语义（核心回归）──────────────────────────────────
def test_stream_appends_incremental_chunks(patch_protocol):
    """append=True 的片段应顺序拼接。"""
    from seed_tools.a2a import a2a_handler

    patch_protocol["client"] = _FakeClient(
        events=[
            _FakeEvent("artifact", text="流", append=True),
            _FakeEvent("artifact", text="式", append=True),
            _FakeEvent("artifact", text="成功", append=True),
            _FakeEvent("status", state="completed"),
        ]
    )
    out = _run(a2a_handler(action="stream", base_url="http://x", message="hi"))
    assert "流式成功" in out
    assert "流流式" not in out


def test_stream_final_snapshot_overrides_chunks(patch_protocol):
    """append=False 是全量快照，必须覆盖而非追加（防重复）。"""
    from seed_tools.a2a import a2a_handler

    patch_protocol["client"] = _FakeClient(
        events=[
            _FakeEvent("artifact", text="流", append=True),
            _FakeEvent("artifact", text="流式", append=True),
            _FakeEvent("artifact", text="流式成功", append=True),
            # 服务端结束时的全量补发
            _FakeEvent("artifact", text="流式成功", append=False),
            _FakeEvent("status", state="completed"),
        ]
    )
    out = _run(a2a_handler(action="stream", base_url="http://x", message="hi"))
    assert "流流式流式成功流式成功" not in out
    assert out.count("流式成功") == 1


def test_stream_reports_session_id(patch_protocol):
    from seed_tools.a2a import a2a_handler

    patch_protocol["client"] = _FakeClient(
        events=[_FakeEvent("status", state="completed", metadata={"sessionId": "a2a-x"})]
    )
    out = _run(a2a_handler(action="stream", base_url="http://x", message="hi"))
    assert "a2a-x" in out


def test_stream_error_event(patch_protocol):
    from seed_tools.a2a import a2a_handler

    patch_protocol["client"] = _FakeClient(events=[_FakeEvent("error", text="boom")])
    out = _run(a2a_handler(action="stream", base_url="http://x", message="hi"))
    assert "boom" in out


# ── 参数校验 ────────────────────────────────────────────────
def test_missing_base_url(patch_protocol):
    from seed_tools.a2a import a2a_handler

    out = _run(a2a_handler(action="send", base_url="", message="hi"))
    assert "base_url" in out


def test_send_requires_message(patch_protocol):
    from seed_tools.a2a import a2a_handler

    out = _run(a2a_handler(action="send", base_url="http://x", message=""))
    assert "message" in out


def test_unknown_action(patch_protocol):
    from seed_tools.a2a import a2a_handler

    out = _run(a2a_handler(action="nope", base_url="http://x", message="hi"))
    assert "未知 action" in out


def test_get_requires_id(patch_protocol):
    from seed_tools.a2a import a2a_handler

    out = _run(a2a_handler(action="get", base_url="http://x"))
    assert "task_id" in out or "context_id" in out


def test_cancel_requires_task_id(patch_protocol):
    from seed_tools.a2a import a2a_handler

    out = _run(a2a_handler(action="cancel", base_url="http://x"))
    assert "task_id" in out


# ── 正常路径 ────────────────────────────────────────────────
def test_send_forwards_context_and_project(patch_protocol):
    from seed_tools.a2a import a2a_handler

    client = _FakeClient()
    patch_protocol["client"] = client
    _run(
        a2a_handler(
            action="send",
            base_url="http://x",
            message="hi",
            context_id="ctx-9",
            project_id="proj-1",
            max_tool_rounds=3,
        )
    )
    _, kwargs = client.sent[0]
    assert kwargs["context_id"] == "ctx-9"
    assert kwargs["project_id"] == "proj-1"
    assert kwargs["max_tool_rounds"] == 3


def test_zero_rounds_means_unlimited(patch_protocol):
    from seed_tools.a2a import a2a_handler

    client = _FakeClient()
    patch_protocol["client"] = client
    _run(a2a_handler(action="send", base_url="http://x", message="hi", max_tool_rounds=0))
    assert client.sent[0][1]["max_tool_rounds"] is None


def test_client_closed_after_call(patch_protocol):
    from seed_tools.a2a import a2a_handler

    client = _FakeClient()
    patch_protocol["client"] = client
    _run(a2a_handler(action="send", base_url="http://x", message="hi"))
    assert client.closed is True


def test_discover_renders_card(patch_protocol):
    from seed_tools.a2a import a2a_handler

    out = _run(a2a_handler(action="discover", base_url="http://x"))
    assert "fake-agent" in out
    assert "JSONRPC" in out


# ── token 解析 ──────────────────────────────────────────────
def test_token_from_env(monkeypatch):
    from seed_tools.a2a import _resolve_token

    monkeypatch.setenv("CODEAGENT_A2A_TOKEN", "env-tok")
    assert _resolve_token("") == "env-tok"
    assert _resolve_token("explicit") == "explicit"


def test_token_empty_when_unset(monkeypatch):
    from seed_tools.a2a import _resolve_token

    monkeypatch.delenv("CODEAGENT_A2A_TOKEN", raising=False)
    assert _resolve_token("") == ""


# ── 注册 ────────────────────────────────────────────────────
def test_a2a_registered_in_toolbox():
    import seed_tools

    registry, _ = seed_tools.setup_builtin_tools()
    assert registry.exists("a2a")
    tool = registry.get("a2a")
    assert tool.category == "agent"
    assert "base_url" in tool.parameters
