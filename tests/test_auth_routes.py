"""codeagent.web.auth_impl 认证路由白名单单元测试（安全回归）。

锁定 is_setup_bootstrap_route / is_public_webui_route 的白名单行为，
防止未来误改导致认证绕过或误拦截。

覆盖：
1. setup 引导路由：setup 相关 API 免 cookie
2. 公开路由：webhook/静态资源/health 等免登录
3. 非白名单路由必须返回 False（受保护）
"""
from codeagent.web import auth_impl as ai


# ---------- is_setup_bootstrap_route ----------
def test_setup_api_prefix_allowed():
    assert ai.is_setup_bootstrap_route("/api/ui/setup/status", "GET") is True
    assert ai.is_setup_bootstrap_route("/api/ui/setup/anything", "POST") is True


def test_setup_llm_presets_get_allowed():
    assert ai.is_setup_bootstrap_route("/api/ui/llm/presets", "GET") is True
    assert ai.is_setup_bootstrap_route("/api/ui/llm/presets", "POST") is True


def test_setup_llm_providers_allowed():
    assert ai.is_setup_bootstrap_route("/api/ui/llm/providers", "GET") is True
    assert ai.is_setup_bootstrap_route("/api/ui/llm/providers", "OPTIONS") is True


def test_setup_presets_test_post_allowed():
    assert ai.is_setup_bootstrap_route("/api/ui/llm/presets/test", "POST") is True
    assert ai.is_setup_bootstrap_route("/api/ui/llm/presets/test", "OPTIONS") is True
    # GET 不在白名单
    assert ai.is_setup_bootstrap_route("/api/ui/llm/presets/test", "GET") is False


def test_setup_env_chat_post_allowed():
    assert ai.is_setup_bootstrap_route("/api/ui/env/chat", "POST") is True
    # GET 不在白名单
    assert ai.is_setup_bootstrap_route("/api/ui/env/chat", "GET") is False


def test_setup_non_whitelisted_denied():
    assert ai.is_setup_bootstrap_route("/api/ui/auth", "POST") is False
    assert ai.is_setup_bootstrap_route("/api/chat", "POST") is False
    assert ai.is_setup_bootstrap_route("/", "GET") is False


# ---------- is_public_webui_route ----------
def test_public_webhook_prefix():
    assert ai.is_public_webui_route("/webhook/anything", "POST") is True


def test_public_setup_and_flags():
    assert ai.is_public_webui_route("/setup", "GET") is True
    assert ai.is_public_webui_route("/api/ui/flags", "GET") is True


def test_public_auth_endpoints():
    assert ai.is_public_webui_route("/api/ui/auth/status", "GET") is True
    assert ai.is_public_webui_route("/api/ui/auth", "POST") is True
    assert ai.is_public_webui_route("/api/ui/auth/logout", "POST") is True


def test_public_llm_providers_get():
    assert ai.is_public_webui_route("/api/ui/llm/providers", "GET") is True


def test_public_file_serve_and_static():
    assert ai.is_public_webui_route("/api/file-serve", "GET") is True
    assert ai.is_public_webui_route("/icon.png", "GET") is True
    assert ai.is_public_webui_route("/health", "GET") is True


def test_public_denies_protected_routes():
    # 受保护路由必须返回 False
    assert ai.is_public_webui_route("/api/ui/env/chat", "GET") is False
    assert ai.is_public_webui_route("/api/chat", "POST") is False
    assert ai.is_public_webui_route("/api/projects", "GET") is False
    assert ai.is_public_webui_route("/api/ui/llm/presets", "POST") is False


def test_public_denies_wrong_method():
    # 白名单限定了 method，错误 method 应拒绝
    assert ai.is_public_webui_route("/setup", "POST") is False
    assert ai.is_public_webui_route("/api/ui/flags", "POST") is False
    assert ai.is_public_webui_route("/icon.png", "POST") is False
