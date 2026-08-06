"""WebUI cookie 按 token 派生改造的回归测试。

覆盖：
1. cookie_name_for 同 token 同名 / 异 token 异名
2. 签发/校验往返、篡改、过期、错误 token 拒绝
3. 中间件：无 cookie 401 / 新名通过 / 旧名 fallback / 异 token 隔离 / 滑动续期注入
4. 完整 API：login 写新名清旧名 / status / logout 删新旧名
"""
import os
import time
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from codeagent.web import auth_impl as ai

TOKEN_A = "token-aaaa"
TOKEN_B = "token-bbbb"


# ---------- 单元层 ----------
def test_cookie_name_derivation():
    assert ai.cookie_name_for(TOKEN_A) == ai.cookie_name_for(TOKEN_A)  # 同 token 同名
    assert ai.cookie_name_for(TOKEN_A) != ai.cookie_name_for(TOKEN_B)  # 异 token 异名
    assert ai.cookie_name_for(TOKEN_A).startswith("ca_webui_")
    assert ai.cookie_name_for(TOKEN_A) != ai.LEGACY_COOKIE_NAME
    assert len(ai.cookie_name_for(TOKEN_A)) == len("ca_webui_") + 8


def test_make_verify_roundtrip():
    ck = ai.make_webui_cookie_value(TOKEN_A)
    assert ai.verify_webui_cookie(TOKEN_A, ck)
    assert not ai.verify_webui_cookie(TOKEN_B, ck)  # 错误 token 拒绝
    assert not ai.verify_webui_cookie(TOKEN_A, ck[:-1] + ("0" if ck[-1] != "0" else "1"))  # 篡改拒绝
    assert not ai.verify_webui_cookie(TOKEN_A, "garbage")
    assert not ai.verify_webui_cookie(TOKEN_A, None)


def test_expired_cookie_rejected():
    exp = str(int(time.time()) - 10).encode()
    sig = ai.hmac.new(ai._cookie_signing_key(TOKEN_A), exp, ai.hashlib.sha256).hexdigest()
    assert not ai.verify_webui_cookie(TOKEN_A, f"{exp.decode()}.{sig}")


def test_get_webui_cookie_value_prefers_new_then_legacy():
    new_name = ai.cookie_name_for(TOKEN_A)
    ck_new = ai.make_webui_cookie_value(TOKEN_A)
    ck_old = ai.make_webui_cookie_value(TOKEN_A)
    # 新名优先
    assert ai.get_webui_cookie_value({new_name: ck_new, ai.LEGACY_COOKIE_NAME: "junk"}, TOKEN_A) == ck_new
    # 缺新名 → 旧名 fallback
    assert ai.get_webui_cookie_value({ai.LEGACY_COOKIE_NAME: ck_old}, TOKEN_A) == ck_old
    # 都没有
    assert ai.get_webui_cookie_value({}, TOKEN_A) is None


# ---------- 中间件集成层 ----------
def _make_app(project_root: Path):
    async def protected(_):
        return JSONResponse({"ok": True})

    async def health(_):
        return JSONResponse({"health": "ok"})

    app = Starlette(
        routes=[
            Route("/api/protected", protected),
            Route("/api/health", health),
        ]
    )
    return ai.WebUIAuthMiddleware(app, project_root=project_root)


def _env(token: str | None):
    if token is None:
        os.environ.pop("CODEAGENT_WEBUI_TOKEN", None)
    else:
        os.environ["CODEAGENT_WEBUI_TOKEN"] = token


def _setup_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="cookie-test-"))
    cfg = root / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "setup.json").write_text('{"done": true}', encoding="utf-8")
    return root


def test_middleware_no_cookie_401():
    _env(TOKEN_A)
    root = _setup_root()
    with TestClient(_make_app(root)) as c:
        r = c.get("/api/protected")
        assert r.status_code == 401, r.text
    _env(None)


def test_middleware_new_name_ok_and_legacy_fallback():
    _env(TOKEN_A)
    root = _setup_root()
    ck = ai.make_webui_cookie_value(TOKEN_A)
    with TestClient(_make_app(root)) as c:
        # 新名
        r = c.get("/api/protected", cookies={ai.cookie_name_for(TOKEN_A): ck})
        assert r.status_code == 200, r.text
        # 旧名 fallback（老用户升级）
        r = c.get("/api/protected", cookies={ai.LEGACY_COOKIE_NAME: ck})
        assert r.status_code == 200, r.text
    _env(None)


def test_middleware_cross_token_isolated():
    """异 token 的 cookie 名不同：各自只认自己的，互不干扰（多实例共存核心）。"""
    _env(TOKEN_A)
    root = _setup_root()
    ck_a = ai.make_webui_cookie_value(TOKEN_A)
    ck_b = ai.make_webui_cookie_value(TOKEN_B)
    name_a = ai.cookie_name_for(TOKEN_A)
    name_b = ai.cookie_name_for(TOKEN_B)
    assert name_a != name_b
    with TestClient(_make_app(root)) as c:
        # 用 token A 的实例：带上 A 和 B 两个 cookie（模拟浏览器同时持有），只认 A
        c.cookies.set(name_a, ck_a)
        c.cookies.set(name_b, ck_b)
        r = c.get("/api/protected")
        assert r.status_code == 200, r.text
    # token B 的实例（换 env 重启中间件）：只认 B，A 的 cookie 无效
    _env(TOKEN_B)
    with TestClient(_make_app(root)) as c:
        c.cookies.set(name_a, ck_a)
        c.cookies.set(name_b, ck_b)
        r = c.get("/api/protected")
        assert r.status_code == 200, r.text
        # 只带 A 的 cookie → 401（B 实例不认 A 的签名）；独立 client 避免 jar 残留
        with TestClient(_make_app(root)) as c2:
            c2.cookies.set(name_a, ck_a)
            r = c2.get("/api/protected")
            assert r.status_code == 401, r.text
    _env(None)


def test_middleware_sliding_refresh_injects_set_cookie():
    _env(TOKEN_A)
    root = _setup_root()
    # 剩余 TTL 远小于一半 → 触发重签
    ck_short = ai.make_webui_cookie_value(TOKEN_A, ttl_sec=60)
    with TestClient(_make_app(root)) as c:
        r = c.get("/api/protected", cookies={ai.cookie_name_for(TOKEN_A): ck_short})
        assert r.status_code == 200
        sc = r.headers.get_list("set-cookie")
        assert any(ai.cookie_name_for(TOKEN_A) in h for h in sc), sc
        assert any("Max-Age=604800" in h for h in sc), sc
    _env(None)


def test_middleware_public_route_ok_without_cookie():
    _env(TOKEN_A)
    root = _setup_root()
    with TestClient(_make_app(root)) as c:
        assert c.get("/api/health").status_code == 200
    _env(None)


def test_middleware_legacy_name_not_refreshed_to_legacy():
    """旧名 cookie 验证通过但不会续期旧名——续期写入新名，完成平滑迁移。"""
    _env(TOKEN_A)
    root = _setup_root()
    ck_short = ai.make_webui_cookie_value(TOKEN_A, ttl_sec=60)
    with TestClient(_make_app(root)) as c:
        r = c.get("/api/protected", cookies={ai.LEGACY_COOKIE_NAME: ck_short})
        assert r.status_code == 200
        sc = r.headers.get_list("set-cookie")
        assert any(ai.cookie_name_for(TOKEN_A) in h for h in sc), sc
    _env(None)


# ---------- 完整 API 层 ----------
def test_api_login_status_logout_flow():
    _env(TOKEN_A)
    root = _setup_root()
    from codeagent.server.webui_api_app import build_webui_api_app

    app = build_webui_api_app(root)
    name_a = ai.cookie_name_for(TOKEN_A)
    # 注意：该 app 内部路由无 /api/ui 前缀（外层 Mount("/api/ui") 挂载）
    with TestClient(app) as c:
        # 初始未登录
        r = c.get("/auth/status")
        assert r.json() == {"auth_required": True, "authenticated": False}

        # 错误 token → 401
        r = c.post("/auth", json={"token": "wrong"})
        assert r.status_code == 401

        # 正确 token → 200，Set-Cookie 新名 + 清旧名
        r = c.post("/auth", json={"token": TOKEN_A})
        assert r.status_code == 200, r.text
        sc = r.headers.get_list("set-cookie")
        assert any(h.startswith(f"{name_a}=") for h in sc), sc
        assert any(h.startswith(f"{ai.LEGACY_COOKIE_NAME}=") and "Max-Age=0" in h for h in sc), sc

        # 登录后 status authenticated
        assert c.get("/auth/status").json()["authenticated"] is True

        # 登出 → 删除新名 + 旧名
        r = c.post("/auth/logout")
        sc = r.headers.get_list("set-cookie")
        names = {h.split("=")[0] for h in sc}
        assert {name_a, ai.LEGACY_COOKIE_NAME} <= names, sc
        assert c.get("/auth/status").json()["authenticated"] is False
    _env(None)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
