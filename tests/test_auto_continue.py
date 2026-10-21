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
    monkeypatch.setattr(ac, "get_pending_plan", lambda a, p: ac.PendingSummary(error="x"))
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
    assert "2 项未完成" in txt
    assert "改 A 模块" in txt
    assert "写测试" in txt
    assert "不要停下来问用户" in txt


def test_nudge_caps_items():
    s = ac.PendingSummary(count=20, items=[{"content": f"t{i}", "status": "pending"} for i in range(20)])
    txt = ac.build_continue_nudge(s)
    assert txt.count("- [") == 6  # 只列前 6 条
    assert "20 项未完成" in txt


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


# ---------- task.md 计划检测（覆盖"做完 Wave 就问要不要继续"） ----------
def _make_task_md(tmp_path, content: str):
    d = tmp_path / ".codeagent" / "default" / "docs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text(content, encoding="utf-8")
    return str(tmp_path)


def test_pending_plan_detects_unchecked(tmp_path, monkeypatch):
    """回归：task.md 有未勾选项 → 视为未完成。"""
    import seed.core.proj_reg as pr

    root = _make_task_md(tmp_path, """# task.md

## Wave 1: 基础 ✅
  - [x] W1.1 完成
  - [x] W1.2 完成

## Wave 2: 首页
  - [ ] W2.1 Hero 区域
  - [ ] W2.2 功能卡片
""")
    monkeypatch.setattr(pr, "resolve_project_path", lambda a, p: root)
    monkeypatch.setattr(ac, "resolve_project_id", lambda a, p: p)
    s = ac.get_pending_plan("default", "proj1")
    assert s.count == 2, f"应检出 2 项，实际 {s.count}"
    assert "Hero" in s.items[0]["content"]


def test_pending_plan_all_done(tmp_path, monkeypatch):
    """全部勾选 → 无未完成。"""
    import seed.core.proj_reg as pr

    root = _make_task_md(tmp_path, """# task.md
## Wave 1
  - [x] W1.1
  - [x] W1.2
""")
    monkeypatch.setattr(pr, "resolve_project_path", lambda a, p: root)
    monkeypatch.setattr(ac, "resolve_project_id", lambda a, p: p)
    assert ac.get_pending_plan("default", "proj1").count == 0


def test_pending_plan_no_file(tmp_path, monkeypatch):
    """无 task.md → 空（不报错）。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "resolve_project_path", lambda a, p: str(tmp_path))
    monkeypatch.setattr(ac, "resolve_project_id", lambda a, p: p)
    assert ac.get_pending_plan("default", "proj1").count == 0


def test_pending_plan_accepts_star_bullets(tmp_path, monkeypatch):
    """兼容 `* [ ]` 写法。"""
    import seed.core.proj_reg as pr

    root = _make_task_md(tmp_path, "# t\n* [ ] 任务A\n* [x] 任务B\n")
    monkeypatch.setattr(pr, "resolve_project_path", lambda a, p: root)
    monkeypatch.setattr(ac, "resolve_project_id", lambda a, p: p)
    assert ac.get_pending_plan("default", "proj1").count == 1


def test_pending_all_merges_sources(monkeypatch):
    """合并 todo + task.md，内容去重。"""
    monkeypatch.setattr(ac, "get_pending_todos", lambda a, p, s="": ac.PendingSummary(
        count=1, items=[{"content": "todo 项", "status": "pending"}],
    ))
    monkeypatch.setattr(ac, "get_pending_plan", lambda a, p: ac.PendingSummary(
        count=2, items=[
            {"content": "todo 项", "status": "pending", "source": "task.md"},  # 重复
            {"content": "计划项", "status": "pending", "source": "task.md"},
        ],
    ))
    s = ac.get_pending_all("default", "proj1")
    assert s.count == 2, f"去重后应为 2，实际 {s.count}"


def test_pending_all_both_empty(monkeypatch):
    monkeypatch.setattr(ac, "get_pending_todos", lambda a, p, s="": ac.PendingSummary())
    monkeypatch.setattr(ac, "get_pending_plan", lambda a, p: ac.PendingSummary())
    assert not ac.get_pending_all("default", "proj1").has_pending


def test_should_continue_uses_plan(monkeypatch):
    """回归：只有 task.md 未完成时也应续跑（核心场景）。"""
    monkeypatch.setattr(ac, "get_pending_todos", lambda a, p, s="": ac.PendingSummary())
    monkeypatch.setattr(ac, "get_pending_plan", lambda a, p: ac.PendingSummary(
        count=2, items=[{"content": "W2.1 Hero", "source": "task.md"}],
    ))
    ok, reason = ac.should_continue("default", "proj1", segments_used=0, max_segments=10)
    assert ok, f"应续跑，实际: {reason}"
    assert "未完成" in reason


def test_nudge_mentions_no_confirm(monkeypatch):
    """nudge 要明确要求"不要请求确认"。"""
    s = ac.PendingSummary(count=1, items=[
        {"content": "W2.1 Hero", "status": "pending", "source": "task.md"},
    ])
    txt = ac.build_continue_nudge(s)
    assert "不要" in txt and "确认" in txt
    assert "task.md" in txt


# ---------- 陈旧待办过滤（防残留 pending 永久阻止停止） ----------
def _iso_hours_ago(h: float) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


def test_stale_pending_ignored(monkeypatch):
    """回归：超过 24h 未更新的 pending 不再阻止停止。

    风险场景：Agent 忘记更新 todo 状态 → 残留 pending → 续跑反复触发。
    """
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    monkeypatch.setattr(pt, "list_todos", lambda a, p, **k: [
        {"id": "1", "content": "陈旧项", "status": "pending",
         "updated_at": _iso_hours_ago(48)},
    ])
    s = ac.get_pending_todos("default", "p1")
    assert s.count == 0, f"陈旧项应被忽略，实际 {s.count}"


def test_fresh_pending_kept(monkeypatch):
    """新鲜的 pending 仍应保留。"""
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    monkeypatch.setattr(pt, "list_todos", lambda a, p, **k: [
        {"id": "1", "content": "新项", "status": "pending",
         "updated_at": _iso_hours_ago(1)},
    ])
    s = ac.get_pending_todos("default", "p1")
    assert s.count == 1


def test_stale_parse_failure_conservative(monkeypatch):
    """时间解析失败 → 保守保留（宁可不漏）。"""
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    monkeypatch.setattr(pt, "list_todos", lambda a, p, **k: [
        {"id": "1", "content": "坏时间", "status": "pending", "updated_at": "not-a-date"},
    ])
    assert ac.get_pending_todos("default", "p1").count == 1


def test_stale_no_timestamp_kept(monkeypatch):
    """无时间戳 → 保守保留。"""
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    monkeypatch.setattr(pt, "list_todos", lambda a, p, **k: [
        {"id": "1", "content": "无时间", "status": "pending"},
    ])
    assert ac.get_pending_todos("default", "p1").count == 1


def test_stale_mixed(monkeypatch):
    """混合：只过滤陈旧的。"""
    import seed.core.proj_reg as pr
    import seed.core.proj_todos as pt

    monkeypatch.setattr(pr, "get_project", lambda a, p: {"id": p, "name": "x"})
    monkeypatch.setattr(pt, "list_todos", lambda a, p, **k: [
        {"id": "1", "content": "陈旧", "status": "pending", "updated_at": _iso_hours_ago(72)},
        {"id": "2", "content": "新鲜", "status": "pending", "updated_at": _iso_hours_ago(2)},
    ])
    s = ac.get_pending_todos("default", "p1")
    assert s.count == 1
    assert s.items[0]["content"] == "新鲜"


# ─────────────── 优先级：项目 todo 优先于 task.md 计划 ───────────────
#
# 规则（见 auto_continue._sort_by_priority）：
#   1（最高）项目 todo —— 当前任务亲手记下的待办
#   2        task.md 计划 —— 项目级，粒度粗、可能过时
#
# 续跑时先做 todo 里明确记下的事，而不是从项目计划重新挑一项。


def test_todo_items_come_before_plan_items():
    """合并后 todo 必须排在 task.md 计划之前。"""
    todos = [
        {"content": "修复登录超时", "status": "in_progress", "source": "todo"},
        {"content": "补测试", "status": "pending", "source": "todo"},
    ]
    plan = [
        {"content": "Wave 3 部署", "source": "task.md"},
        {"content": "Wave 4 验收", "source": "task.md"},
    ]
    ordered = ac._sort_by_priority(todos, plan)
    contents = [str(it.get("content")) for it in ordered]
    assert contents == [
        "修复登录超时",
        "补测试",
        "Wave 3 部署",
        "Wave 4 验收",
    ], f"优先级顺序错误：{contents}"


def test_sort_by_priority_is_stable_within_same_level():
    """同优先级内保持原有相对顺序，不擅自重排。"""
    todos = [{"content": f"T{i}", "source": "todo"} for i in range(5)]
    plan = [{"content": f"P{i}", "source": "task.md"} for i in range(5)]
    ordered = ac._sort_by_priority(todos, plan)
    assert [str(it["content"]) for it in ordered][:5] == [f"T{i}" for i in range(5)]


def test_dedup_keeps_todo_when_text_identical_to_plan_item():
    """文本相同时必须保留 todo，丢弃 plan 项（不能反之）。"""
    todos = [{"content": "同名字项", "status": "pending", "source": "todo"}]
    plan = [{"content": "同名字项", "source": "task.md"}]

    # 复刻 get_pending_all 的去重逻辑（含 _sort_by_priority）
    merged, seen = [], set()
    for it in ac._sort_by_priority(todos, plan):
        key = str(it.get("content") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(it)

    assert len(merged) == 1, f"去重后应只剩 1 项，实际 {len(merged)}"
    assert merged[0].get("source") == "todo", (
        f"去重时应保留 todo，实际保留了 {merged[0].get('source')}"
    )


def test_nudge_puts_todo_section_before_plan_section():
    """nudge 必须把「优先处理的 todo」排在「项目计划」之前。"""
    summary = ac.PendingSummary(
        count=3,
        items=[
            {"content": "修复登录超时", "status": "in_progress", "source": "todo"},
            {"content": "补测试", "status": "pending", "source": "todo"},
            {"content": "Wave 3 部署", "source": "task.md"},
        ],
    )
    text = ac.build_continue_nudge(summary)
    i_todo = text.find("修复登录超时")
    i_plan = text.find("Wave 3 部署")
    assert i_todo != -1 and i_plan != -1, f"nudge 缺少待办或计划项：\n{text}"
    assert i_todo < i_plan, f"nudge 中 todo 应排在 plan 之前：\n{text}"
    assert "优先处理" in text, "nudge 未标注 todo 为优先项"


def test_nudge_todo_only_has_no_plan_section():
    """只有 todo 时不应出现「项目计划」分组。"""
    summary = ac.PendingSummary(
        count=1,
        items=[{"content": "只有 todo", "status": "pending", "source": "todo"}],
    )
    text = ac.build_continue_nudge(summary)
    assert "只有 todo" in text
    assert "task.md" not in text, f"无计划项时不应提及 task.md：\n{text}"


def test_nudge_plan_only_still_renders():
    """只有 task.md 计划时仍能正常输出（不因分组逻辑崩掉）。"""
    summary = ac.PendingSummary(
        count=2,
        items=[
            {"content": "Wave 3 部署", "source": "task.md"},
            {"content": "Wave 4 验收", "source": "task.md"},
        ],
    )
    text = ac.build_continue_nudge(summary)
    assert "Wave 3 部署" in text and "Wave 4 验收" in text
    assert "优先处理" not in text, "无 todo 时不应出现优先分组"
