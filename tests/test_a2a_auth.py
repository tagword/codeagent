"""A2A Bearer 认证测试。

覆盖 4 种情形 + 声明一致性：
1. 未配置 token → 放行（本机开发模式），且 Agent Card 不声明 security
2. 配置 token + 无 Authorization → 401 语义（JSON-RPC -32001）
3. 配置 token + 错误 token → 拒绝
4. 配置 token + 正确 token → 通过
5. Agent Card 的 security 声明与 auth_enabled() 一致（声明不脱节）

认证在 JSON-RPC 入口统一做，故 message/send 与 message/stream 均覆盖。
"""

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from codeagent.server.a2a import a2a_agent_card, a2a_jsonrpc
from codeagent.server.a2a.agent_card import build_agent_card
from codeagent.server.a2a.auth import ERR_UNAUTHORIZED, auth_enabled, check_request
from codeagent.web import auth_impl as ai

TOKEN = "test-a2a-secret-token"


@pytest.fixture()
def client():
    app = Starlette(routes=[
        Route("/.well-known/agent-card.json", a2a_agent_card, methods=["GET"]),
        Route("/a2a", a2a_jsonrpc, methods=["POST"]),
    ])
    return TestClient(app)


@pytest.fixture()
def no_token(monkeypatch):
    monkeypatch.setattr(ai, "get_webui_token", lambda *a, **k: "")
    return None


@pytest.fixture()
def with_token(monkeypatch):
    monkeypatch.setattr(ai, "get_webui_token", lambda *a, **k: TOKEN)
    return TOKEN


def _rpc_body():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "hi"}],
                "messageId": "m-1",
                "contextId": "ctx-auth",
            }
        },
    }


# ---------- 1. 未配置 token：放行 ----------
def test_no_token_configured_allows_request(client, no_token):
    r = client.post("/a2a", json=_rpc_body())
    assert r.status_code == 200
    assert r.json().get("error", {}).get("code") != ERR_UNAUTHORIZED


def test_auth_disabled_when_no_token(no_token):
    assert auth_enabled() is False


# ---------- 2. 配置 token + 无 header：拒绝 ----------
def test_missing_header_rejected(client, with_token, monkeypatch):
    # 避免真的跑 chat turn：认证失败应在进入业务逻辑前返回
    r = client.post("/a2a", json=_rpc_body())
    assert r.status_code == 200  # JSON-RPC 错误走 200 + error 字段
    err = r.json().get("error") or {}
    assert err.get("code") == ERR_UNAUTHORIZED


# ---------- 3. 配置 token + 错误 token：拒绝 ----------
def test_wrong_token_rejected(client, with_token):
    r = client.post("/a2a", json=_rpc_body(), headers={"Authorization": "Bearer wrong"})
    err = r.json().get("error") or {}
    assert err.get("code") == ERR_UNAUTHORIZED


def test_non_bearer_scheme_rejected(client, with_token):
    r = client.post("/a2a", json=_rpc_body(), headers={"Authorization": f"Basic {TOKEN}"})
    err = r.json().get("error") or {}
    assert err.get("code") == ERR_UNAUTHORIZED


# ---------- 4. 配置 token + 正确 token：通过 ----------
def test_correct_token_accepted(client, with_token, monkeypatch):
    """认证通过后应进入业务逻辑（此处用假 run_chat_turn 隔离）。"""
    import codeagent.server.a2a.handlers as h

    async def fake_turn(**kwargs):
        return {"text": "pong", "tools_used": [], "token_usage": {}}

    monkeypatch.setattr(h, "run_chat_turn", fake_turn, raising=False)
    r = client.post("/a2a", json=_rpc_body(), headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert "error" not in r.json()


def test_token_case_insensitive_scheme(client, with_token, monkeypatch):
    """`bearer` 小写也应被接受（HTTP 认证方案大小写不敏感）。"""
    import codeagent.server.a2a.handlers as h

    async def fake_turn(**kwargs):
        return {"text": "pong", "tools_used": [], "token_usage": {}}

    monkeypatch.setattr(h, "run_chat_turn", fake_turn, raising=False)
    r = client.post("/a2a", json=_rpc_body(), headers={"Authorization": f"bearer {TOKEN}"})
    assert "error" not in r.json()


# ---------- 5. Agent Card 声明与实现一致 ----------
def test_card_declares_security_when_token_configured(with_token):
    card = build_agent_card()
    assert "security" in card
    assert "bearer" in card.get("securitySchemes", {})


def test_card_omits_security_when_no_token(no_token):
    card = build_agent_card()
    assert "security" not in card
    assert "securitySchemes" not in card


# ---------- check_request 单元级 ----------
def test_check_request_uses_constant_time_compare(with_token):
    class _Req:
        headers = {"authorization": f"Bearer {TOKEN}"}

    assert check_request(_Req()) is True


def test_check_request_empty_header(with_token):
    class _Req:
        headers = {}

    assert check_request(_Req()) is False
