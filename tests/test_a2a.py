"""A2A 协议适配层测试。

覆盖：
1. Agent Card 结构合法（发现端点）
2. JSON-RPC 入口：未知方法 / 非法 JSON / 缺参数
3. message/send：正常 → Task(completed)；异常 → Task(failed)
4. contextId 连续性：同 contextId → 同 session
5. 认证白名单：A2A 端点可通过中间件

run_chat_turn 被 monkeypatch 成假实现，测试不触网。
"""

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from codeagent.server.a2a import a2a_agent_card, a2a_jsonrpc
from codeagent.server.a2a.agent_card import build_agent_card
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
    # security 声明与 auth_enabled() 一致（未配置 token 时不声明），
    # 两种状态各自的行为由 test_a2a_auth.py 覆盖。
    from codeagent.server.a2a.auth import auth_enabled

    assert ("securitySchemes" in card) is auth_enabled()


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


# ---------- 项目校验默认放行 ----------
@pytest.fixture(autouse=True)
def _no_a2a_auth(monkeypatch):
    """禁用 A2A 认证，隔离本机 config/webui.token 的影响。

    认证行为由 tests/test_a2a_auth.py 专门覆盖；本文件测的是协议逻辑，
    若读取真实 token 文件，所有用例都会因缺 Bearer 头而 401。
    """
    monkeypatch.setattr(ai, "get_webui_token", lambda *a, **k: "")


@pytest.fixture(autouse=True)
def _allow_any_project(monkeypatch):
    """默认认为任意 projectId 都存在，避免每个测试都要 mock。

    需要验证「不存在的项目降级」的测试自行覆盖此 fixture。
    """
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda aid, pid: {"project_id": pid})


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


# ---------- projectId 贯通（Message.metadata）----------
def test_project_id_from_message_metadata(client, fake_chat_turn):
    """projectId 走 A2A 原生 Message.metadata，并回传到 Task.metadata。"""
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-p1", "method": "message/send",
        "params": {"message": {
            "role": "user", "contextId": "ctx-proj",
            "parts": [{"kind": "text", "text": "hi"}],
            "metadata": {"projectId": "proj-meta"},
        }},
    })
    result = r.json()["result"]
    assert fake_chat_turn[0]["project_id"] == "proj-meta"
    assert result["metadata"]["projectId"] == "proj-meta"
    assert result["metadata"]["inferredFromTask"] is False


def test_project_id_metadata_wins_over_configuration(client, fake_chat_turn):
    """message.metadata.projectId 优先于 configuration.projectId。"""
    client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-p2", "method": "message/send",
        "params": {
            "message": {
                "role": "user", "contextId": "ctx-proj2",
                "parts": [{"kind": "text", "text": "hi"}],
                "metadata": {"projectId": "from-meta"},
            },
            "configuration": {"projectId": "from-cfg"},
        },
    })
    assert fake_chat_turn[0]["project_id"] == "from-meta"


def test_project_id_fallback_to_configuration(client, fake_chat_turn):
    """无 metadata 时回退 configuration.projectId（向后兼容）。"""
    client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-p3", "method": "message/send",
        "params": {
            "message": {"role": "user", "contextId": "ctx-proj3",
                        "parts": [{"kind": "text", "text": "hi"}]},
            "configuration": {"projectId": "legacy-cfg"},
        },
    })
    assert fake_chat_turn[0]["project_id"] == "legacy-cfg"


def test_no_project_id_yields_empty(client, fake_chat_turn):
    """都不传时为空串，由存储层归入 __unassigned__。"""
    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-p4", "method": "message/send",
        "params": {"message": {"role": "user", "contextId": "ctx-proj4",
                               "parts": [{"kind": "text", "text": "hi"}]}},
    })
    assert fake_chat_turn[0]["project_id"] == ""
    assert r.json()["result"]["metadata"]["projectId"] == ""


# ---------- taskId → contextId 反查（规范 MUST）----------
def test_task_id_infers_context(client, fake_chat_turn, monkeypatch):
    """只传 taskId 时从 Task 反查 contextId，不新建上下文。"""
    from codeagent.server.a2a import context as ctx_mod

    monkeypatch.setattr(ctx_mod, "context_id_for_task", lambda tid: "ctx-from-task")

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-t1", "method": "message/send",
        "params": {"message": {
            "role": "user", "taskId": "task-known",
            "parts": [{"kind": "text", "text": "继续"}],
        }},
    })
    result = r.json()["result"]
    assert result["contextId"] == "ctx-from-task"
    assert result["metadata"]["sessionId"] == "a2a-ctx-from-task"
    assert result["metadata"]["inferredFromTask"] is True


def test_context_task_mismatch_rejected(client, fake_chat_turn, monkeypatch):
    """规范 MUST：contextId 与 taskId 不匹配时拒绝请求。"""
    from codeagent.server.a2a import context as ctx_mod

    monkeypatch.setattr(ctx_mod, "context_id_for_task", lambda tid: "ctx-real")

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-t2", "method": "message/send",
        "params": {"message": {
            "role": "user", "contextId": "ctx-wrong", "taskId": "task-x",
            "parts": [{"kind": "text", "text": "hi"}],
        }},
    })
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == -32602
    assert "mismatch" in body["error"]["message"]


def test_tasks_get_by_task_id_only(client, monkeypatch):
    """tasks/get 只传 id 时也能反查 contextId。"""
    from codeagent.server.a2a import handlers as h

    monkeypatch.setattr(h, "context_id_for_task", lambda tid: "ctx-lookup")

    class _Sess:
        messages = [{"role": "assistant", "content": "历史回复"}]
        metadata = {"project_id": "proj-lookup"}

    import seed.core.llm_sess as ls
    monkeypatch.setattr(ls, "load_chat_session_from_disk", lambda *a, **k: _Sess())

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-g1", "method": "tasks/get",
        "params": {"id": "task-known"},
    })
    result = r.json()["result"]
    assert result["contextId"] == "ctx-lookup"
    assert result["metadata"]["projectId"] == "proj-lookup"
    assert result["artifacts"][0]["parts"][0]["text"] == "历史回复"


# ---------- projectId 校验（防会话静默丢失）----------
def test_unknown_project_id_degrades_to_unassigned(client, fake_chat_turn, monkeypatch):
    """不存在的 projectId 必须降级为空，否则 persist 会因外键失败丢会话。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda aid, pid: None)

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-v1", "method": "message/send",
        "params": {"message": {
            "role": "user", "contextId": "ctx-badproj",
            "parts": [{"kind": "text", "text": "hi"}],
            "metadata": {"projectId": "proj-ghost"},
        }},
    })
    assert fake_chat_turn[0]["project_id"] == ""
    assert r.json()["result"]["metadata"]["projectId"] == ""


def test_existing_project_id_preserved(client, fake_chat_turn, monkeypatch):
    """存在的 projectId 原样透传。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda aid, pid: {"project_id": pid})

    client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-v2", "method": "message/send",
        "params": {"message": {
            "role": "user", "contextId": "ctx-goodproj",
            "parts": [{"kind": "text", "text": "hi"}],
            "metadata": {"projectId": "proj-real"},
        }},
    })
    assert fake_chat_turn[0]["project_id"] == "proj-real"


# ---------- 续聊继承项目归属 ----------
def test_continuation_inherits_project(client, fake_chat_turn, monkeypatch):
    """续聊未显式传 projectId 时，沿用会话已归属的项目，避免归属漂移。"""
    import seed.core.llm_sess as ls

    class _Sess:
        metadata = {"project_id": "proj-inherited"}

    monkeypatch.setattr(ls, "load_chat_session_from_disk", lambda *a, **k: _Sess())

    r = client.post("/a2a", json={
        "jsonrpc": "2.0", "id": "req-i1", "method": "message/send",
        "params": {"message": {
            "role": "user", "contextId": "ctx-inherit",
            "parts": [{"kind": "text", "text": "继续"}],
        }},
    })
    assert fake_chat_turn[0]["project_id"] == "proj-inherited"
    assert r.json()["result"]["metadata"]["projectId"] == "proj-inherited"
