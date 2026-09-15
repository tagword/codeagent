"""A2A 协议适配层测试。

覆盖：
1. Agent Card 结构合法（发现端点）
2. JSON-RPC 入口：未知方法 / 非法 JSON / 缺参数
3. message/send：正常 → Task(completed)；异常 → Task(failed)
4. contextId 连续性：同 contextId → 同 session
5. 认证白名单：A2A 端点可通过中间件

run_chat_turn 被 monkeypatch 成假实现，测试不触网。
"""
import json

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from codeagent.server.a2a import a2a_agent_card, a2a_jsonrpc
from codeagent.server.a2a.agent_card import build_agent_card
from codeagent.server.a2a import handlers as a2a_handlers
from codeagent.web import auth_impl as ai


@pytest.fixture()
def client():
    app = Starlette(routes=[
        Route("/.well-known/agent-card.json", a2a_agent_card, methods=["GET"]),
        Route("/a2a", a2a_jsonrpc, methods=["POST"]),
    ])
    return TestClient(app)


# ---------- Agent Card ----------
def test_agent_card_structure():
    card = build_agent_card()
    assert card["protocolVersion"]
    assert card["name"] == "codeagent-rsi"
    assert card["url"].endswith("/a2a")
    assert "capabilities" in card
    assert isinstance(card["skills"], list) and card["skills"]
    skill = card["skills"][0]
    for key in ("id", "name", "description", "inputModes", "outputModes"):
        assert key in skill
    assert "securitySchemes" in card


def test_agent_card_endpoint(client):
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "codeagent-rsi"
    assert data["skills"][0]["id"] == "dev-task"


# ---------- JSON-RPC 错误路径 ----------
def test_unknown_method(client):
    r = client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "nope"})
    assert r.status_code == 200
    err = r.json()["error"]
    assert err["code"] == -32601


def test_invalid_json(client):
    r = client.post("/a2a", content=b"not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32700


def test_missing_message(client):
    r = client.post("/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "message/send", "params": {}})
    assert r.json()["error"]["code"] == -32602


def test_empty_text(client):
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": 3, "method": "message/send",
        "params": {"message": {"role": "user", "parts": []}},
    })
    assert r.json()["error"]["code"] == -32602


# ---------- message/send 正常路径 ----------
@pytest.fixture()
def fake_chat_turn(monkeypatch):
    """把 run_chat_turn 换成假实现，记录调用参数。"""
    calls = []

    async def _fake(**kwargs):
        calls.append(kwargs)
        return {
            "reply": f"已处理：{kwargs['user_msg']['content']}",
            "session_id": kwargs["session_id"],
            "tools_used": ["file_read"],
            "token_usage": {"total_tokens": 100},
            "cost": {"total_cost": 0.01, "currency": "CNY"},
            "model": "fake-model",
        }

    import codeagent.server.chat_turn as ct
    monkeypatch.setattr(ct, "run_chat_turn", _fake)
    return calls


def test_send_message_completed(client, fake_chat_turn):
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-1", "method": "message/send",
        "params": {"message": {
            "role": "user", "messageId": "m1",
            "parts": [{"kind": "text", "text": "修复缺陷"}],
        }},
    })
    result = r.json()["result"]
    assert result["kind"] == "task"
    assert result["status"]["state"] == "completed"
    assert result["artifacts"][0]["parts"][0]["text"] == "已处理：修复缺陷"
    assert result["metadata"]["sessionId"].startswith("a2a-")
    assert result["metadata"]["toolsUsed"] == ["file_read"]
    # 验证 run_chat_turn 收到正确参数
    assert fake_chat_turn[0]["channel"] == "A2A"
    assert fake_chat_turn[0]["emit_ws"] is False


def test_context_continuity(client, fake_chat_turn):
    """同 contextId 两次调用 → 同一 session_id。"""
    payload = {
        "jsonrpc": "2.0", "id": "req-2", "method": "message/send",
        "params": {"message": {
            "role": "user", "contextId": "ctx-fixed",
            "parts": [{"kind": "text", "text": "第一轮"}],
        }},
    }
    r1 = client.post("/a2a", json=payload)
    payload["params"]["message"]["parts"][0]["text"] = "第二轮"
    r2 = client.post("/a2a", json=payload)

    s1 = r1.json()["result"]["metadata"]["sessionId"]
    s2 = r2.json()["result"]["metadata"]["sessionId"]
    assert s1 == s2 == "a2a-ctx-fixed"
    assert r1.json()["result"]["contextId"] == "ctx-fixed"


def test_send_message_failure(client, monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import codeagent.server.chat_turn as ct
    monkeypatch.setattr(ct, "run_chat_turn", _boom)

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-3", "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"text": "x"}]}},
    })
    result = r.json()["result"]
    assert result["status"]["state"] == "failed"
    assert "boom" in result["artifacts"][0]["parts"][0]["text"]


def test_max_tool_rounds_passthrough(client, fake_chat_turn):
    client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-4", "method": "message/send",
        "params": {
            "message": {"role": "user", "parts": [{"text": "x"}]},
            "configuration": {"maxToolRounds": 7, "projectId": "proj-1"},
        },
    })
    assert fake_chat_turn[0]["max_tool_rounds"] == 7
    assert fake_chat_turn[0]["project_id"] == "proj-1"


# ---------- tasks/get ----------
def test_tasks_get_missing_context(client):
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "g1", "method": "tasks/get", "params": {},
    })
    assert r.json()["error"]["code"] == -32602


def test_tasks_get_context_not_found(client):
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "g2", "method": "tasks/get",
        "params": {"contextId": "ctx-does-not-exist-xyz"},
    })
    assert r.json()["error"]["code"] == -32602
    assert "not found" in r.json()["error"]["message"]


def test_tasks_get_from_disk(client, monkeypatch):
    """tasks/get 从磁盘加载 session（服务重启后内存清空也能查到）。"""
    class _FakeSess:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello from disk"},
        ]

    import seed.core.llm_sess as ls
    monkeypatch.setattr(ls, "load_chat_session_from_disk",
                        lambda *a, **k: _FakeSess())

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "g3", "method": "tasks/get",
        "params": {"contextId": "ctx-any"},
    })
    result = r.json()["result"]
    assert result["status"]["state"] == "completed"
    assert result["artifacts"][0]["parts"][0]["text"] == "hello from disk"
    assert result["metadata"]["messageCount"] == 2


# ---------- 认证白名单 ----------
def test_a2a_routes_public():
    assert ai.is_public_webui_route("/.well-known/agent-card.json", "GET")
    assert ai.is_public_webui_route("/a2a", "POST")
    # 非 A2A 路径仍受保护
    assert not ai.is_public_webui_route("/api/chat", "POST")
