"""Tests for codeagent.server.team_engine — team workflow execution.

Isolates runs/teams dirs via monkeypatch so nothing touches the real
~/.codeagent. Uses simulate=True for the engine tests (no LLM required) and
exercises the pure helper functions directly.
"""

from __future__ import annotations

import json
import time

import pytest

import codeagent.server.team_engine as eng


def _patch_dirs(monkeypatch, tmp_path):
    # 与真实 _teams_dir/_runs_dir 一致：访问时 mkdir(parents=True)
    def _td():
        p = tmp_path / "teams"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _rd():
        p = tmp_path / "runs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(eng, "_teams_dir", _td)
    monkeypatch.setattr(eng, "_runs_dir", _rd)


def _mk_team(monkeypatch, tmp_path, team_id="t1", **overrides):
    _patch_dirs(monkeypatch, tmp_path)
    td = tmp_path / "teams"
    td.mkdir(parents=True, exist_ok=True)
    data = {
        "name": team_id,
        "members": ["default", "default"],
        "mode": "sequential",
        "error_policy": "stop",
        "timeout_seconds": 60,
    }
    data.update(overrides)
    (td / f"{team_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _wait_done(run_id, timeout=30.0):
    """Poll run until it leaves 'running' (or timeout).

    Background daemon threads can be starved under full-suite CPU load, so use a
    generous timeout to avoid flakes.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = eng.get_run(run_id)
        if run and run.get("status") != "running":
            return run
        time.sleep(0.05)
    return eng.get_run(run_id)


# ── helper: _member_agent_id ─────────────────────────────────────

def test_member_agent_id_str():
    assert eng._member_agent_id("ag_1") == "ag_1"


def test_member_agent_id_dict():
    assert eng._member_agent_id({"id": "ag_1"}) == "ag_1"
    assert eng._member_agent_id({"agent_id": "ag_2"}) == "ag_2"
    assert eng._member_agent_id({"role": "PM"}) == "PM"


def test_member_agent_id_empty():
    assert eng._member_agent_id({}) == ""
    assert eng._member_agent_id("") == ""


# ── helper: _split_subtasks ──────────────────────────────────────

def test_split_subtasks_simple_lines():
    out = "1. 写登录 API\n2. 写注册 API\n3. 测试"
    parts = eng._split_subtasks(out, 3)
    assert parts == ["写登录 API", "写注册 API", "测试"]


def test_split_subtasks_dash_and_bullet():
    out = "- 前端页面\n- 后端接口\n- 联调"
    parts = eng._split_subtasks(out, 3)
    assert parts == ["前端页面", "后端接口", "联调"]


def test_split_subtasks_fewer_lines_than_n_pads():
    parts = eng._split_subtasks("只拆出一个任务", 3)
    assert len(parts) == 3
    assert parts[0] == "只拆出一个任务"


def test_split_subtasks_more_lines_than_n_buckets():
    out = "\n".join(f"{i}. 子任务{i}" for i in range(1, 6))
    parts = eng._split_subtasks(out, 2)
    assert len(parts) == 2
    assert "子任务1" in parts[0]
    assert "子任务5" in parts[1]


def test_split_subtasks_empty_output():
    parts = eng._split_subtasks("", 2)
    assert parts == []


def test_split_subtasks_zero_workers_no_crash():
    # n<=0 不应抛 ZeroDivisionError —— 退化为单桶（全部行并到一个子任务）
    assert eng._split_subtasks("1. a\n2. b", 0) == ["a\nb"]
    assert eng._split_subtasks("1. a", 0) == ["a"]


# ── run_team: simulate=True 全流程 ───────────────────────────────

def test_run_team_team_not_found(tmp_path, monkeypatch):
    _patch_dirs(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        eng.run_team("missing", "hi")


def test_run_team_sequential_simulate_done(tmp_path, monkeypatch):
    _mk_team(monkeypatch, tmp_path, mode="sequential", members=["a1", "a2"])
    run = eng.run_team("t1", "hello", simulate=True)
    assert run["status"] == "running"  # 立即返回，后台执行
    final = _wait_done(run["id"])
    assert final["status"] == "done"
    steps = final["steps"]
    assert len(steps) == 2
    assert all(s["type"] == "sequential" for s in steps)
    assert all(s["status"] == "done" for s in steps)
    assert "[模拟]" in steps[0]["output"]


def test_run_team_parallel_simulate_done(tmp_path, monkeypatch):
    _mk_team(monkeypatch, tmp_path, mode="parallel", members=["a1", "a2", "a3"])
    run = eng.run_team("t1", "hello", simulate=True)
    final = _wait_done(run["id"])
    assert final["status"] == "done"
    assert len(final["steps"]) == 3
    assert all(s["type"] == "parallel" for s in final["steps"])


def test_run_team_manager_simulate_done(tmp_path, monkeypatch):
    _mk_team(monkeypatch, tmp_path, mode="manager", members=["pm", "w1", "w2"], manager_id="pm")
    run = eng.run_team("t1", "hello", simulate=True)
    final = _wait_done(run["id"])
    assert final["status"] == "done"
    types = [s["type"] for s in final["steps"]]
    assert types.count("manager-pm") == 1
    assert types.count("manager-worker") == 2


def test_run_team_manager_no_workers_simulate(tmp_path, monkeypatch):
    # 只有 PM 一个成员 —— worker 为空，run 仍应 done
    _mk_team(monkeypatch, tmp_path, mode="manager", members=["solo"], manager_id="solo")
    run = eng.run_team("t1", "hello", simulate=True)
    final = _wait_done(run["id"])
    assert final["status"] == "done"


def test_run_team_unknown_mode_fails_immediately(tmp_path, monkeypatch):
    _mk_team(monkeypatch, tmp_path, mode="bogus", members=["a1"])
    run = eng.run_team("t1", "hello", simulate=True)
    assert run["status"] == "failed"
    assert "Unknown mode" in run.get("error", "")


# ── run/step 持久化辅助 ──────────────────────────────────────────

def test_create_and_update_run(tmp_path, monkeypatch):
    _patch_dirs(monkeypatch, tmp_path)
    run = eng.create_run("t1", "input")
    assert run["status"] == "pending"
    updated = eng.update_run(run["id"], {"status": "running"})
    assert updated["status"] == "running"
    got = eng.get_run(run["id"])
    assert got["team_id"] == "t1"


def test_add_and_update_step(tmp_path, monkeypatch):
    _patch_dirs(monkeypatch, tmp_path)
    run = eng.create_run("t1", "input")
    step = eng.add_step(run["id"], "agent1", "sequential")
    assert step["status"] == "pending"
    eng.update_step(run["id"], step["step_id"], {"status": "done", "output": "out"})
    final = eng.get_run(run["id"])
    assert final["steps"][0]["status"] == "done"
    assert final["steps"][0]["output"] == "out"


# ── role_prompt 真实化（A 形态角色扮演打通） ─────────────────────

def test_member_role_prompt_helper():
    assert eng._member_role_prompt("plain") == ""          # str 无 role
    assert eng._member_role_prompt({"id": "a1"}) == ""     # dict 无 role
    assert eng._member_role_prompt({"id": "a1", "role": "PM"}) == ""  # role 字段不用作 prompt
    assert eng._member_role_prompt({"id": "a1", "system_prompt": "你是前端"}) == "你是前端"
    assert eng._member_role_prompt({"id": "a1", "role_prompt": "你是后端"}) == "你是后端"


def test_real_sequential_passes_role_prompt(tmp_path, monkeypatch):
    """dict member 的 system_prompt 应传入 run_member_step_meta 的 role_prompt。"""
    from codeagent.server import team_worker as tw

    captured = {}
    def fake_step(*, agent_id, task, role_prompt="", **kw):
        captured[agent_id] = {"task": task, "role_prompt": role_prompt}
        return f"out-{agent_id}", {"total_tokens": 10}
    monkeypatch.setattr(tw, "run_member_step_meta", fake_step)

    _patch_dirs(monkeypatch, tmp_path)
    run = eng.create_run("t1", "hi")
    rid = run["id"]
    members = [
        {"id": "fe", "system_prompt": "你是前端工程师"},
        {"id": "be", "role_prompt": "你是后端工程师"},
    ]
    eng._real_sequential(rid, members, "做个功能", "stop", 60)
    assert captured["fe"]["role_prompt"] == "你是前端工程师"
    assert captured["be"]["role_prompt"] == "你是后端工程师"
    # context 传递：be 的 task 是 fe 的 output
    assert "out-fe" in captured["be"]["task"]
    # usage 应记录到 step
    final = eng.get_run(rid)
    assert final["steps"][0].get("usage", {}).get("total_tokens") == 10


def test_real_manager_passes_worker_role_prompt(tmp_path, monkeypatch):
    """manager 模式 worker 的 role_prompt 应传入。"""
    from codeagent.server import team_worker as tw

    captured = {}
    def fake_step(*, agent_id, task, role_prompt="", **kw):
        captured[agent_id] = {"task": task, "role_prompt": role_prompt}
        if agent_id == "pm":
            return "1. 子任务A\n2. 子任务B", {"total_tokens": 5}
        return f"out-{agent_id}", {"total_tokens": 7}
    monkeypatch.setattr(tw, "run_member_step_meta", fake_step)

    _patch_dirs(monkeypatch, tmp_path)
    run = eng.create_run("t1", "hi")
    rid = run["id"]
    members = [
        {"id": "pm", "system_prompt": "你是技术负责人"},
        {"id": "w1", "role_prompt": "你是测试"},
        {"id": "w2", "role_prompt": "你是文档"},
    ]
    eng._real_manager(rid, members, "做个项目", "stop", 60, manager_id="pm")
    assert captured["pm"]["role_prompt"] == "你是技术负责人"
    assert captured["w1"]["role_prompt"] == "你是测试"
    assert captured["w2"]["role_prompt"] == "你是文档"
    assert "子任务A" in captured["w1"]["task"]


# ── rerun_run（失败 run 恢复重跑） ────────────────────────

def test_rerun_run_reexecutes_and_clears_steps(tmp_path, monkeypatch):
    """rerun_run 应清空旧步骤、重置为 running、后台重跑同团队同输入。"""
    _patch_dirs(monkeypatch, tmp_path)
    # 建团队文件
    td = eng._teams_dir()
    td.mkdir(parents=True, exist_ok=True)
    (td / "t1.json").write_text(json.dumps({"name": "t1", "members": ["a1", "a2"], "mode": "sequential"}), encoding="utf-8")
    # 手动造一个 failed run（带旧步骤）
    run = eng.create_run("t1", "input")
    rid = run["id"]
    eng.update_run(rid, {"status": "failed", "error": "boom", "steps": [{"step_id": "old", "status": "failed", "output": "x"}]})
    # rerun（simulate 模式，不调真实 LLM）
    updated = eng.rerun_run(rid, simulate=True)
    assert updated["status"] == "running"
    assert not updated.get("error")
    assert updated["steps"] == []  # 旧步骤已清
    # 等待后台线程跑完
    done = _wait_done(rid)
    assert done["status"] == "done"
    assert len(done["steps"]) == 2  # 两个成员各一步（simulate）


# ── sweep_stale_runs（卡死 run 惰性清理） ────────────────────

def test_sweep_stale_runs_marks_old_running_as_timeout(tmp_path, monkeypatch):
    """running 且长时间无进展的 run 应被标记 timeout；新 running 不动。"""
    _patch_dirs(monkeypatch, tmp_path)
    # 建团队（timeout 默认 300）
    td = eng._teams_dir()
    td.mkdir(parents=True, exist_ok=True)
    (td / "t1.json").write_text(json.dumps({"name": "t1", "members": ["a1"], "mode": "sequential"}), encoding="utf-8")

    # 一条 running 但 updated_at 很旧（模拟线程挂死）
    stale = eng.create_run("t1", "in")
    eng.update_run(stale["id"], {"status": "running"})
    # 直接把 updated_at 拨回 1 小时前
    import time as _t
    eng.update_run(stale["id"], {"status": "running"})
    f = eng._runs_dir() / (stale["id"] + ".json")
    data = json.loads(f.read_text(encoding="utf-8"))
    data["updated_at"] = _t.time() - 3600
    f.write_text(json.dumps(data), encoding="utf-8")

    # 一条 running 但刚更新（健康）
    fresh = eng.create_run("t1", "in2")
    eng.update_run(fresh["id"], {"status": "running"})

    cleared = eng.sweep_stale_runs()
    assert cleared == 1
    assert eng.get_run(stale["id"])["status"] == "timeout"
    assert eng.get_run(fresh["id"])["status"] == "running"


# ── cancel_run（手动停止 running run） ─────────────────────

def test_cancel_run_stops_running(tmp_path, monkeypatch):
    """cancel_run 把 running run 标 timeout；done/failed 不受影响。"""
    _patch_dirs(monkeypatch, tmp_path)
    td = eng._teams_dir()
    td.mkdir(parents=True, exist_ok=True)
    (td / "t1.json").write_text(json.dumps({"name": "t1", "members": ["a1"], "mode": "sequential"}), encoding="utf-8")
    run = eng.create_run("t1", "in")
    eng.update_run(run["id"], {"status": "running"})
    stopped = eng.cancel_run(run["id"])
    assert stopped["status"] == "timeout"
    assert "手动" in stopped.get("error", "")
    # done run 不应被取消
    d = eng.create_run("t1", "in2")
    eng.update_run(d["id"], {"status": "done"})
    assert eng.cancel_run(d["id"])["status"] == "done"
    # 不存在返回 None
    assert eng.cancel_run("nope") is None


# ── 健壮性：成员校验 / 并发上限 / usage 提取 ─────────────────

def test_validate_members_rules(tmp_path, monkeypatch):
    """成员校验：空/缺失/重复/PM 不在成员中 都应拒绝。"""
    _patch_dirs(monkeypatch, tmp_path)
    # 隔离 agents 根目录（避免污染真实 ~/.codeagent/agents）
    agents_root = tmp_path / "agents"
    agents_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(eng, "_agents_root", lambda: agents_root)
    (agents_root / "realagent" / "persona").mkdir(parents=True, exist_ok=True)

    # 空成员
    with pytest.raises(ValueError, match="至少需要 1 个成员"):
        eng.validate_members([], "")
    # 成员不存在
    with pytest.raises(ValueError, match="不存在"):
        eng.validate_members(["ghost"], "")
    # 重复
    with pytest.raises(ValueError, match="重复"):
        eng.validate_members(["realagent", "realagent"], "")
    # PM 不在成员中
    with pytest.raises(ValueError, match="不在团队成员"):
        eng.validate_members(["realagent"], "other")
    # 合法通过
    eng.validate_members(["realagent"], "realagent")
    # dict 成员
    eng.validate_members([{"id": "realagent", "role_prompt": "x"}], "realagent")


def test_parallel_workers_cap():
    """并行线程数应被 _PARALLEL_MAX_WORKERS 封顶。"""
    assert eng._parallel_workers(0) == 1
    assert eng._parallel_workers(1) == 1
    assert eng._parallel_workers(3) == 3
    assert eng._parallel_workers(100) == eng._PARALLEL_MAX_WORKERS
    assert eng._parallel_workers(100) <= 6


def test_extract_usage_robust():
    """usage 提取应容错缺省字段。"""
    from codeagent.server.team_worker import _extract_usage
    assert _extract_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 5}})["total_tokens"] == 15
    assert _extract_usage({"usage": {"total_tokens": 99}})["total_tokens"] == 99
    assert _extract_usage(None)["total_tokens"] == 0
    assert _extract_usage({})["total_tokens"] == 0
    assert _extract_usage({"usage": "bad"})["total_tokens"] == 0
