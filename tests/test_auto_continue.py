"""未完成事项驱动续跑测试。"""

from codeagent.server import auto_continue as ac


# ---------- PendingSummary ----------
def test_pending_summary_empty():
    s = ac.PendingSummary()
    assert not s.has_pending
    assert s.count == 0


def test_pending_summary_with_items():
    s = ac.PendingSummary(count=2, items=[{"content": "a"}, {"content": "b"}])
    assert s.has_pending
    assert s.to_dict()["count"] == 2


# ---------- get_pending_todos ----------
def test_no_project_returns_empty():
    """无 project_id 时保守返回空（不查）。"""
    s = ac.get_pending_todos("default", "")
    assert not s.has_pending


def test_query_failure_conservative(monkeypatch):
    """查询失败时保守返回空，不抛异常。"""
    import seed.core.proj_todos as pt

    def _boom(*a, **k):
        raise RuntimeError("store corrupted")

    monkeypatch.setattr(pt, "list_todos", _boom)
    s = ac.get_pending_todos("default", "proj1")
    assert not s.has_pending
    assert s.error


def test_filters_by_status(monkeypatch):
    """只统计 pending/in_progress，忽略 completed。"""
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: [
        {"id": "1", "content": "未做", "status": "pending"},
        {"id": "2", "content": "在做", "status": "in_progress"},
        {"id": "3", "content": "做完", "status": "completed"},
        {"id": "4", "content": "取消", "status": "cancelled"},
    ])
    s = ac.get_pending_todos("default", "proj1")
    assert s.count == 2
    assert {i["id"] for i in s.items} == {"1", "2"}


def test_status_case_insensitive(monkeypatch):
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: [
        {"id": "1", "content": "x", "status": "PENDING"},
        {"id": "2", "content": "y", "status": "In_Progress"},
    ])
    assert ac.get_pending_todos("default", "p").count == 2


def test_malformed_items_ignored(monkeypatch):
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: [
        "not a dict", None, {"id": "1", "content": "ok", "status": "pending"},
    ])
    assert ac.get_pending_todos("default", "p").count == 1


# ---------- should_continue ----------
def test_should_continue_when_pending(monkeypatch):
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: [
        {"id": "1", "content": "改代码", "status": "pending"},
    ])
    ok, reason = ac.should_continue("default", "p", segments_used=0, max_segments=4)
    assert ok
    assert "1 项未完成" in reason


def test_should_not_continue_when_done(monkeypatch):
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: [
        {"id": "1", "content": "x", "status": "completed"},
    ])
    ok, reason = ac.should_continue("default", "p")
    assert not ok
    assert "无未完成" in reason


def test_should_not_continue_at_limit(monkeypatch):
    """硬上限优先：即使有未完成，达上限也停（防失控）。"""
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: [
        {"id": "1", "content": "x", "status": "pending"},
    ])
    ok, reason = ac.should_continue("default", "p", segments_used=4, max_segments=4)
    assert not ok
    assert "上限" in reason


def test_should_not_continue_on_error(monkeypatch):
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pt, "list_todos", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    ok, reason = ac.should_continue("default", "p")
    assert not ok
    assert "保守停止" in reason


# ---------- build_continue_nudge ----------
def test_nudge_empty_when_no_pending():
    assert ac.build_continue_nudge(ac.PendingSummary()) == ""


def test_nudge_lists_items():
    s = ac.PendingSummary(count=2, items=[
        {"content": "改 A 模块", "status": "pending"},
        {"content": "写测试", "status": "in_progress"},
    ])
    txt = ac.build_continue_nudge(s)
    assert "2 项待办" in txt
    assert "改 A 模块" in txt
    assert "写测试" in txt
    assert "不要停下等用户" in txt


def test_nudge_caps_items():
    s = ac.PendingSummary(count=20, items=[{"content": f"t{i}", "status": "pending"} for i in range(20)])
    txt = ac.build_continue_nudge(s)
    assert txt.count("- [") == 5  # 只列前 5 条
    assert "20 项待办" in txt


# ---------- 回归：project_id 解析（端到端实测发现） ----------
def test_resolve_valid_id_passthrough(monkeypatch):
    """已是有效 id → 原样返回。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    assert ac.resolve_project_id("default", "98100283705d") == "98100283705d"


def test_resolve_name_to_id(monkeypatch):
    """回归：传名字（如 ui-proj）应解析成真实 id。

    真实场景：A2A 传 projectId=ui-proj，list_todos 查不到 → 续跑静默失效。
    """
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda a, p: None)
    monkeypatch.setattr(pr, "list_projects", lambda a: [
        {"id": "ce55d710b2b4", "name": "ui-proj", "path": "/home/u2/agent/.rsi/workspace/ui-proj"},
        {"id": "98100283705d", "name": "codeagent", "path": "/home/u2/agent"},
    ])
    assert ac.resolve_project_id("default", "ui-proj") == "ce55d710b2b4"


def test_resolve_by_path_suffix(monkeypatch):
    """按路径尾段匹配。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda a, p: None)
    monkeypatch.setattr(pr, "list_projects", lambda a: [
        {"id": "abc123", "name": "other", "path": "/home/u2/projects/myapp"},
    ])
    assert ac.resolve_project_id("default", "myapp") == "abc123"


def test_resolve_unknown_returns_input(monkeypatch):
    """解析失败 → 返回原值（调用方保守处理）。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda a, p: None)
    monkeypatch.setattr(pr, "list_projects", lambda a: [])
    assert ac.resolve_project_id("default", "nonexistent") == "nonexistent"


def test_resolve_empty():
    assert ac.resolve_project_id("default", "") == ""


def test_resolve_error_conservative(monkeypatch):
    """解析异常不崩。"""
    import seed.core.proj_reg as pr

    def _boom(*a, **k):
        raise RuntimeError("registry corrupt")

    monkeypatch.setattr(pr, "get_project", _boom)
    assert ac.resolve_project_id("default", "x") == "x"


def test_get_pending_uses_resolved_id(monkeypatch):
    """端到端：传名字也能查到 todo。"""
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: None)
    monkeypatch.setattr(pr, "list_projects", lambda a: [
        {"id": "realid123", "name": "ui-proj", "path": "/x/ui-proj"},
    ])
    called = {}

    def _list(aid, pid, **k):
        called["pid"] = pid
        return [{"id": "1", "content": "待办", "status": "pending"}]

    monkeypatch.setattr(pt, "list_todos", _list)
    s = ac.get_pending_todos("default", "ui-proj")
    assert called["pid"] == "realid123", f"未解析：{called['pid']}"
    assert s.count == 1


# ---------- 回归：不按 session 过滤（端到端实测发现） ----------
def test_no_session_filter(monkeypatch):
    """回归：待办是项目级的，不能按 session 过滤。

    真实场景：A2A 会话 id 是 a2a-ctx-xxx，与 todo 创建时的 session_id
    不同 → 精确匹配查不到 → 续跑静默失效。
    """
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    captured = {}

    def _list(aid, pid, **kw):
        captured.update(kw)
        return [{"id": "1", "content": "跨会话待办", "status": "pending"}]

    monkeypatch.setattr(pt, "list_todos", _list)
    s = ac.get_pending_todos("default", "proj1", "a2a-ctx-abc")
    assert "session_id" not in captured, f"不应传 session_id：{captured}"
    assert s.count == 1, "跨会话待办应可见"
