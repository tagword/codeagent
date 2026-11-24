"""跨项目会话隔离测试。

历史 bug：内存会话缓存键 ``_memkey(agent, session)`` 不含 project_id，
导致两个项目使用相同 session_id（如都叫 ``web-chat``）时共用同一份内存
Session 对象 —— 项目 B 的消息会追加进项目 A 的上下文，且 project_id 被覆盖。

磁盘持久化本身按项目目录隔离，只有内存缓存这一层会串。
"""
from __future__ import annotations

from codeagent.server import _memkey
from seed.core._session_cache import SESSIONS


def test_memkey_includes_project():
    a = _memkey("default", "web-chat", "proj-A")
    b = _memkey("default", "web-chat", "proj-B")
    assert a != b, "跨项目同名 session 必须产生不同缓存键"
    assert "proj-A" in a and "proj-B" in b


def test_memkey_same_project_same_key():
    assert _memkey("default", "s1", "p1") == _memkey("default", "s1", "p1")


def test_memkey_without_project_is_backward_compatible():
    """未传 project_id 时退化为旧格式，保证 cron / 旧调用点不炸。"""
    assert _memkey("default", "web-chat") == "default::web-chat"
    assert _memkey("default", "web-chat", "") == "default::web-chat"


def test_memkey_handles_whitespace_and_empty_agent():
    assert _memkey("", "s1", "p1") == _memkey("default", "s1", "p1")
    assert _memkey(" default ", "s1", "p1") == _memkey("default", "s1", "p1")


def test_cross_project_sessions_do_not_share_memory():
    """端到端：两个项目同名 session 各自持有独立消息列表。"""
    SESSIONS.clear()
    try:
        ka = _memkey("default", "web-chat", "proj-A")
        kb = _memkey("default", "web-chat", "proj-B")

        SESSIONS[ka] = {"project_id": "proj-A", "messages": []}
        SESSIONS[ka]["messages"].append("项目A的问题")

        # 项目 B 走同样的 key 计算 → 必须未命中缓存
        assert kb not in SESSIONS, "项目B 不应命中项目A 的缓存"
        SESSIONS[kb] = {"project_id": "proj-B", "messages": []}
        SESSIONS[kb]["messages"].append("项目B的问题")

        assert SESSIONS[ka]["messages"] == ["项目A的问题"]
        assert SESSIONS[kb]["messages"] == ["项目B的问题"]
        assert SESSIONS[ka] is not SESSIONS[kb]
    finally:
        SESSIONS.clear()


def test_chat_turn_passes_project_id_to_memkey():
    """回归守卫：chat_turn 的 _memkey 调用必须带 project_id。"""
    import inspect

    from codeagent.server import chat_turn

    src = inspect.getsource(chat_turn)
    # 不允许出现两参数的旧写法
    assert "_memkey(agent_id, session_id)" not in src, (
        "chat_turn 存在未带 project_id 的 _memkey 调用，会导致跨项目串台"
    )


def test_app_factory_session_endpoints_pass_project_id():
    """回归守卫：app_factory 中会话相关的 _memkey 调用必须带 project_id。"""
    import inspect

    from codeagent.server import app_factory

    src = inspect.getsource(app_factory)
    assert "_memkey(agent_id, session_id)" not in src, (
        "app_factory 存在未带 project_id 的 _memkey 调用"
    )
    assert "_memkey(aid, sid)" not in src, (
        "app_factory 存在未带 project_id 的 _memkey(aid, sid) 调用"
    )


def test_webui_handlers_sessions_pass_project_id():
    import inspect

    from codeagent.server import webui_handlers_sessions

    src = inspect.getsource(webui_handlers_sessions)
    assert "_memkey(aid, sid)" not in src, (
        "webui_handlers_sessions 存在未带 project_id 的 _memkey 调用"
    )
