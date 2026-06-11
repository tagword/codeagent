"""Team workflow engine — executes multi-agent team runs.

Three modes:
- sequential: members run one after another, passing context
- parallel: all members run simultaneously
- manager: first member is PM who splits and dispatches to others

Each run is persisted as a JSON file in ~/.codeagent/runs/
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from codeagent.core.paths import codeagent_home

logger = logging.getLogger(__name__)

RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_DONE = "done"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_TIMEOUT = "timeout"

STEP_STATUS_PENDING = "pending"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_DONE = "done"
STEP_STATUS_FAILED = "failed"


def _runs_dir() -> Path:
    p = codeagent_home() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _teams_dir() -> Path:
    p = codeagent_home() / "teams"
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_runs(team_id: str | None = None, limit: int = 50) -> list[dict]:
    """List runs, optionally filtered by team_id."""
    rd = _runs_dir()
    runs = []
    for f in sorted(rd.glob("*.json"), reverse=True):
        if len(runs) >= limit:
            break
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["id"] = f.stem
            if team_id and data.get("team_id") != team_id:
                continue
            runs.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return runs


def create_run(team_id: str, user_input: str) -> dict:
    """Create a new run record and return it."""
    run_id = uuid.uuid4().hex[:12]
    run = {
        "team_id": team_id,
        "user_input": user_input,
        "status": RUN_STATUS_PENDING,
        "created_at": time.time(),
        "updated_at": time.time(),
        "steps": [],
    }
    f = _runs_dir() / f"{run_id}.json"
    f.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    run["id"] = run_id
    return run


def get_run(run_id: str) -> dict | None:
    """Get run by id."""
    f = _runs_dir() / f"{run_id}.json"
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        data["id"] = run_id
        return data
    except (json.JSONDecodeError, OSError):
        return None


def update_run(run_id: str, updates: dict) -> dict | None:
    """Update run fields."""
    f = _runs_dir() / f"{run_id}.json"
    if not f.is_file():
        return None
    data = get_run(run_id)
    if data is None:
        return None
    data.update(updates)
    data["updated_at"] = time.time()
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def add_step(run_id: str, agent_id: str, step_type: str) -> dict | None:
    """Add a step to a run, return the step."""
    run = get_run(run_id)
    if run is None:
        return None
    step = {
        "step_id": uuid.uuid4().hex[:8],
        "agent_id": agent_id,
        "type": step_type,
        "status": STEP_STATUS_PENDING,
        "input": "",
        "output": "",
        "created_at": time.time(),
    }
    run["steps"].append(step)
    update_run(run_id, {"steps": run["steps"]})
    return step


def update_step(run_id: str, step_id: str, updates: dict) -> dict | None:
    """Update a step within a run."""
    run = get_run(run_id)
    if run is None:
        return None
    for step in run["steps"]:
        if step.get("step_id") == step_id:
            step.update(updates)
            break
    update_run(run_id, {"steps": run["steps"]})
    return run


def run_team(team_id: str, user_input: str) -> dict:
    """Execute a team workflow. Returns immediately with run_id; actual execution is simulated.

    For a real implementation, this would spin up agents via the chat API.
    """
    # Load team
    tf = _teams_dir() / f"{team_id}.json"
    if not tf.is_file():
        raise ValueError(f"Team '{team_id}' not found")
    team = json.loads(tf.read_text(encoding="utf-8"))
    team["id"] = team_id

    # Create run
    run = create_run(team_id, user_input)
    run_id = run["id"]
    update_run(run_id, {"status": RUN_STATUS_RUNNING})

    mode = team.get("mode", "sequential")
    members = team.get("members", [])
    error_policy = team.get("error_policy", "stop")
    timeout = team.get("timeout_seconds", 300)

    if mode == "sequential":
        _run_sequential(run_id, members, user_input, error_policy, timeout)
    elif mode == "parallel":
        _run_parallel(run_id, members, user_input, error_policy, timeout)
    elif mode == "manager":
        _run_manager(run_id, members, user_input, error_policy, timeout, manager_id=team.get("manager_id", ""))
    else:
        update_run(run_id, {"status": RUN_STATUS_FAILED, "error": f"Unknown mode: {mode}"})

    update_run(run_id, {"status": RUN_STATUS_DONE})
    return get_run(run_id) or run


def _run_sequential(run_id: str, members: list, user_input: str, error_policy: str, timeout: int) -> None:
    """Run members one after another, passing context."""
    context = user_input
    for member in members:
        agent_id = member if isinstance(member, str) else member.get("id", "")
        step = add_step(run_id, agent_id, "sequential")
        if step is None:
            return
        update_step(run_id, step["step_id"], {"status": STEP_STATUS_RUNNING, "input": context})
        # Simulate execution (in real impl, this calls the agent)
        time.sleep(0.5)
        output = f"[模拟] Agent '{agent_id}' 处理完成:\n收到: {context[:100]}..."
        update_step(run_id, step["step_id"], {"status": STEP_STATUS_DONE, "output": output})
        context = output


def _run_parallel(run_id: str, members: list, user_input: str, error_policy: str, timeout: int) -> None:
    """Run all members simultaneously."""
    import concurrent.futures

    def _run_one(agent_id: str) -> tuple[str, str, str]:
        step = add_step(run_id, agent_id, "parallel")
        sid = step["step_id"] if step else ""
        update_step(run_id, sid, {"status": STEP_STATUS_RUNNING, "input": user_input})
        time.sleep(0.3)
        output = f"[模拟] Agent '{agent_id}' 并行处理完成"
        update_step(run_id, sid, {"status": STEP_STATUS_DONE, "output": output})
        return agent_id, sid, output

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(members)) as pool:
        futures = []
        for member in members:
            agent_id = member if isinstance(member, str) else member.get("id", "")
            futures.append(pool.submit(_run_one, agent_id))
        concurrent.futures.wait(futures)


def _run_manager(run_id: str, members: list, user_input: str, error_policy: str, timeout: int, manager_id: str = "") -> None:
    """First member is PM who dispatches to others. If manager_id is set, that member is PM."""
    if not members:
        return
    # 显式指定的管家优先，否则取第一个成员
    pm_id = manager_id if manager_id and manager_id in [m if isinstance(m, str) else m.get("id", "") for m in members] else (members[0] if isinstance(members[0], str) else members[0].get("id", ""))
    workers = members[1:] if len(members) > 1 else []

    # PM step: analyze and split
    pm_step = add_step(run_id, pm_id, "manager-pm")
    if pm_step is None:
        return
    update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_RUNNING, "input": user_input})
    time.sleep(0.5)
    pm_output = f"[模拟] PM '{pm_id}' 将任务拆分为 {max(len(workers), 1)} 个子任务"
    update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_DONE, "output": pm_output})

    # Worker steps
    for i, worker in enumerate(workers):
        wid = worker if isinstance(worker, str) else worker.get("id", "")
        w_step = add_step(run_id, wid, "manager-worker")
        if w_step is None:
            return
        update_step(run_id, w_step["step_id"], {
            "status": STEP_STATUS_RUNNING,
            "input": f"子任务 {i+1}: {user_input[:80]}..."
        })
        time.sleep(0.3)
        w_output = f"[模拟] Worker '{wid}' 完成子任务 {i+1}"
        update_step(run_id, w_step["step_id"], {"status": STEP_STATUS_DONE, "output": w_output})
