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


def _wait_done(run_id, timeout=10.0):
    """Poll run until it leaves 'running' (or timeout)."""
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
