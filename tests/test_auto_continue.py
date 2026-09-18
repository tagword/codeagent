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
