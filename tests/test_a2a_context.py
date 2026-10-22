"""a2a/context.py 单测：ID 解析、projectId 校验、taskId 登记与反查。

与 ``test_a2a.py`` 的分工：
- ``test_a2a.py`` 走 HTTP 端到端，反查函数被 mock（关注协议行为）
- 本文件直接测 context 模块内部逻辑（关注反查/登记的真实实现）
"""

from __future__ import annotations

import pytest

from codeagent.server.a2a import context as ctx
from codeagent.server.a2a.models import Message, Part


def _msg(**kw) -> Message:
    kw.setdefault("parts", [Part(kind="text", text="hi")])
    return Message(**kw)


@pytest.fixture(autouse=True)
def _project_exists(monkeypatch):
    """默认任意 projectId 都存在，个别用例自行覆盖。"""
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda aid, pid: {"project_id": pid})


# ---------- resolve：ID 解析 ----------
def test_resolve_generates_ids_when_absent():
    r = ctx.resolve(_msg(), {})
    assert r.context_id.startswith("ctx-")
    assert r.task_id.startswith("task-")
    assert r.session_id == f"a2a-{r.context_id}"
    assert r.inferred_from_task is False


def test_resolve_keeps_given_context_id():
    r = ctx.resolve(_msg(context_id="ctx-1"), {})
    assert r.context_id == "ctx-1"
    assert r.session_id == "a2a-ctx-1"


def test_resolve_infers_context_from_task(monkeypatch):
    monkeypatch.setattr(ctx, "context_id_for_task", lambda tid: "ctx-found")
    r = ctx.resolve(_msg(task_id="task-1"), {})
    assert r.context_id == "ctx-found"
    assert r.inferred_from_task is True


def test_resolve_unknown_task_falls_back_to_new_context(monkeypatch):
    """反查不到不能串到别人上下文，按新会话处理。"""
    monkeypatch.setattr(ctx, "context_id_for_task", lambda tid: "")
    r = ctx.resolve(_msg(task_id="task-ghost"), {})
    assert r.context_id != ""
    assert r.inferred_from_task is False
    assert r.task_id == "task-ghost"


def test_resolve_rejects_context_task_mismatch(monkeypatch):
    monkeypatch.setattr(ctx, "context_id_for_task", lambda tid: "ctx-real")
    with pytest.raises(ctx.ContextError):
        ctx.resolve(_msg(context_id="ctx-wrong", task_id="task-1"), {})


def test_resolve_accepts_matching_pair(monkeypatch):
    monkeypatch.setattr(ctx, "context_id_for_task", lambda tid: "ctx-real")
    r = ctx.resolve(_msg(context_id="ctx-real", task_id="task-1"), {})
    assert r.context_id == "ctx-real"
    assert r.inferred_from_task is False


# ---------- resolve：projectId ----------
def test_project_id_from_metadata_wins():
    r = ctx.resolve(
        _msg(context_id="c", metadata={"projectId": "from-meta"}),
        {"projectId": "from-cfg"},
    )
    assert r.project_id == "from-meta"


def test_project_id_falls_back_to_configuration():
    r = ctx.resolve(_msg(context_id="c"), {"projectId": "from-cfg"})
    assert r.project_id == "from-cfg"


def test_unknown_project_degrades_to_empty(monkeypatch):
    import seed.core.proj_reg as pr

    monkeypatch.setattr(pr, "get_project", lambda aid, pid: None)
    r = ctx.resolve(_msg(context_id="c", metadata={"projectId": "ghost"}), {})
    assert r.project_id == ""


def test_project_lookup_error_degrades_to_empty(monkeypatch):
    import seed.core.proj_reg as pr

    def _boom(aid, pid):
        raise RuntimeError("registry down")

    monkeypatch.setattr(pr, "get_project", _boom)
    r = ctx.resolve(_msg(context_id="c", metadata={"projectId": "p"}), {})
    assert r.project_id == ""


# ---------- context_id_for_task：反查 ----------
def _patch_sessions(monkeypatch, sessions: dict[str, object]):
    """sessions: session_id → 会话对象（None 表示加载失败）。"""
    import seed.core.llm_sess as ls

    monkeypatch.setattr(
        ls,
        "list_stored_sessions_meta",
        lambda limit=300, agent_id="default": [
            {"session_id": sid, "project_id": "p"} for sid in sessions
        ],
    )
    monkeypatch.setattr(
        ls,
        "load_chat_session_from_disk",
        lambda sid, agent_id="default", project_id=None: sessions.get(sid),
    )


class _Sess:
    def __init__(self, metadata):
        self.metadata = metadata


def test_context_id_for_task_hit(monkeypatch):
    _patch_sessions(monkeypatch, {
        "a2a-ctx-a": _Sess({"a2a_tasks": ["task-old"]}),
        "a2a-ctx-b": _Sess({"a2a_tasks": ["task-new"]}),
    })
    assert ctx.context_id_for_task("task-new") == "ctx-b"


def test_context_id_for_task_skips_non_a2a_sessions(monkeypatch):
    _patch_sessions(monkeypatch, {"sess-x": _Sess({"a2a_tasks": ["task-1"]})})
    assert ctx.context_id_for_task("task-1") == ""


def test_context_id_for_task_misses_and_errors(monkeypatch):
    _patch_sessions(monkeypatch, {"a2a-ctx-a": None})
    assert ctx.context_id_for_task("task-none") == ""

    import seed.core.llm_sess as ls

    def _boom(*a, **k):
        raise RuntimeError("disk error")

    monkeypatch.setattr(ls, "list_stored_sessions_meta", _boom)
    assert ctx.context_id_for_task("task-1") == ""


# ---------- record_task：登记 ----------
class _RecordingStore:
    def __init__(self, sessions):
        self.sessions = sessions
        self.persisted: list[_Sess] = []


@pytest.fixture()
def store(monkeypatch):
    """把 load/persist 替换为内存实现。"""
    sessions = {"a2a-ctx-a": _Sess({})}
    rec = _RecordingStore(sessions)
    import seed.core.llm_sess as ls

    monkeypatch.setattr(
        ls,
        "load_chat_session_from_disk",
        lambda sid, agent_id="default", project_id=None: sessions.get(sid),
    )
    monkeypatch.setattr(
        ls, "persist_chat_session", lambda sess, agent_id="default": rec.persisted.append(sess)
    )
    return rec


def test_record_task_appends(store):
    ctx.record_task("a2a-ctx-a", "task-1")
    assert store.sessions["a2a-ctx-a"].metadata["a2a_tasks"] == ["task-1"]
    assert len(store.persisted) == 1


def test_record_task_dedupes(store):
    ctx.record_task("a2a-ctx-a", "task-1")
    ctx.record_task("a2a-ctx-a", "task-1")
    assert store.sessions["a2a-ctx-a"].metadata["a2a_tasks"] == ["task-1"]
    assert len(store.persisted) == 1


def test_record_task_caps_history(store):
    for i in range(60):
        ctx.record_task("a2a-ctx-a", f"task-{i}")
    tasks = store.sessions["a2a-ctx-a"].metadata["a2a_tasks"]
    assert len(tasks) == 50
    assert tasks[-1] == "task-59"
    assert tasks[0] == "task-10"


def test_record_task_missing_session_is_noop(store):
    ctx.record_task("a2a-missing", "task-1")
    assert store.persisted == []


def test_record_task_empty_task_is_noop(store):
    ctx.record_task("a2a-ctx-a", "")
    assert store.persisted == []
