"""跨项目会话隔离测试（codeagent 侧）。

根因修复在 ``seed.core._session_cache._memkey``（已加 project_id 维度）。
本文件验证 **codeagent 的各个调用点确实把 project_id 传了下去** —— 只修
_memkey 而调用点不传，等于没修。

历史 bug：两个项目使用相同 session_id（如都叫 ``web-chat``）时共用同一份
内存 Session 对象，项目 B 的消息追加进项目 A 的上下文，且 project_id 被覆盖。
磁盘持久化本身按项目目录隔离，只有内存缓存这一层会串。
"""
from __future__ import annotations

import inspect

from codeagent.server import _memkey
from seed.core._session_cache import SESSIONS


def test_memkey_is_seed_implementation():
    """codeagent 直接复用 seed 的实现，不再本地覆盖（避免两处逻辑分叉）。"""
    from seed.core._session_cache import _memkey as seed_memkey

    assert _memkey is seed_memkey


def test_memkey_includes_project():
    a = _memkey("default", "web-chat", "proj-A")
    b = _memkey("default", "web-chat", "proj-B")
    assert a != b, "跨项目同名 session 必须产生不同缓存键"
    assert "proj-A" in a and "proj-B" in b


def test_memkey_without_project_is_backward_compatible():
    """未传 project_id 时退化为旧格式，保证 cron / 旧调用点不炸。"""
    assert _memkey("default", "web-chat") == "default::web-chat"
    assert _memkey("default", "web-chat", "") == "default::web-chat"


def test_cross_project_sessions_do_not_share_memory():
    """端到端：两个项目同名 session 各自持有独立消息列表。"""
    SESSIONS.clear()
    try:
        ka = _memkey("default", "web-chat", "proj-A")
        kb = _memkey("default", "web-chat", "proj-B")

        SESSIONS[ka] = {"project_id": "proj-A", "messages": []}
        SESSIONS[ka]["messages"].append("项目A的问题")

        assert kb not in SESSIONS, "项目B 不应命中项目A 的缓存"
        SESSIONS[kb] = {"project_id": "proj-B", "messages": []}
        SESSIONS[kb]["messages"].append("项目B的问题")

        assert SESSIONS[ka]["messages"] == ["项目A的问题"]
        assert SESSIONS[kb]["messages"] == ["项目B的问题"]
        assert SESSIONS[ka] is not SESSIONS[kb]
    finally:
        SESSIONS.clear()


# ── 调用点守卫：禁止出现不带 project_id 的 _memkey 调用 ──

def test_chat_turn_passes_project_id_to_memkey():
    from codeagent.server import chat_turn

    src = inspect.getsource(chat_turn)
    assert "_memkey(agent_id, session_id)" not in src, (
        "chat_turn 存在未带 project_id 的 _memkey 调用，会导致跨项目串台"
    )


def test_app_factory_session_endpoints_pass_project_id():
    from codeagent.server import app_factory

    src = inspect.getsource(app_factory)
    assert "_memkey(agent_id, session_id)" not in src, (
        "app_factory 存在未带 project_id 的 _memkey 调用"
    )
    assert "_memkey(aid, sid)" not in src, (
        "app_factory 存在未带 project_id 的 _memkey(aid, sid) 调用"
    )


def test_webui_handlers_sessions_pass_project_id():
    from codeagent.server import webui_handlers_sessions

    src = inspect.getsource(webui_handlers_sessions)
    assert "_memkey(aid, sid)" not in src, (
        "webui_handlers_sessions 存在未带 project_id 的 _memkey 调用"
    )


def test_load_or_create_chat_session_passes_project_id():
    """app_factory 加载会话时必须带 project_id，否则会读写错项目的文件。"""
    from codeagent.server import app_factory

    src = inspect.getsource(app_factory)
    assert "load_or_create_chat_session(session_id, agent_id)" not in src, (
        "app_factory 存在未带 project_id 的 load_or_create_chat_session 调用"
    )
