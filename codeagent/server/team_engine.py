"""Team workflow engine — executes multi-agent team runs.

Three modes:
- sequential: members run one after another, passing context
- parallel: all members run simultaneously
- manager: first member is PM who splits and dispatches to others

Each run is persisted as a JSON file in ~/.codeagent/runs/
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
import uuid
from pathlib import Path

from codeagent.core.paths import codeagent_home

logger = logging.getLogger(__name__)

# 持久化读写锁：run 文件是「读-改-写」共享状态，真实执行在后台线程/并行
# 模式下会并发触碰同一 run 文件，必须串行化防丢更新。
_RUN_LOCK = threading.RLock()

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
    _maybe_sweep_stale()  # 惰性清理卡死的 running run
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


# ── 卡死 run 清理（watchdog 惰性扫描） ──────────────────────────
# 后台执行线程若中途崩溃 / 进程重启 / LLM 调用挂死，run 会永久停在 running。
# 没有常驻 watchdog 线程（避免又引入需管理的后台进程），改为在 list_runs 时
# 惰性扫描：带时间门控，最多每 _SWEEP_INTERVAL 秒全扫一次。
_SWEEP_INTERVAL = 30.0
_last_sweep = [0.0]  # 模块级单例，避免每次 list 都全扫

# 一个 run 允许的"无进展"最大时长（秒）：超过视为后台线程卡死。
# 团队级 timeout_seconds 目前只存不生效（见 _real_* 未用 timeout），这里作为
# 兜底判定：running run 的 updated_at 超过该值未刷新即标记 timeout。
# 下限 60s：健康 run 每步都会刷新 updated_at，只有线程真挂死才会超时。
_STALE_MIN_FLOOR = 60.0


def sweep_stale_runs() -> int:
    """把超过时限仍 running 的 run 标记为 timeout，返回清理条数。

    判定：run.status == running 且 now - run.updated_at > 该 run 的 team
    timeout（缺省 300s，下限 _STALE_MIN_FLOOR 防误杀长生成）。
    """
    import time as _t
    rd = _runs_dir()
    cleared = 0
    now = _t.time()
    for f in rd.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") != RUN_STATUS_RUNNING:
            continue
        updated = float(data.get("updated_at") or data.get("created_at") or 0)
        # 团队 timeout 配置可能缺失/过小，取下限 _STALE_MIN_FLOOR 防误杀
        team_timeout = 300.0
        team_id = data.get("team_id") or ""
        if team_id:
            tf = _teams_dir() / f"{team_id}.json"
            if tf.is_file():
                try:
                    team_timeout = float(json.loads(tf.read_text(encoding="utf-8")).get("timeout_seconds") or 300.0)
                except (json.JSONDecodeError, OSError, ValueError):
                    team_timeout = 300.0
        max_age = max(team_timeout, _STALE_MIN_FLOOR)
        if now - updated > max_age:
            run_id = f.stem
            with _RUN_LOCK:
                update_run(run_id, {"status": RUN_STATUS_TIMEOUT, "error": "运行超过时限被标记为超时（后台线程可能已挂起）"})
            cleared += 1
    return cleared


def _maybe_sweep_stale() -> None:
    """带时间门控的惰性清理：最多每 _SWEEP_INTERVAL 秒全扫一次。"""
    now = time.time()
    if now - _last_sweep[0] >= _SWEEP_INTERVAL:
        try:
            sweep_stale_runs()
        except Exception:  # noqa: BLE001 — 清理失败不应影响列表读取
            logger.warning("sweep_stale_runs failed", exc_info=True)
        _last_sweep[0] = time.time()


def cancel_run(run_id: str) -> dict | None:
    """手动强制结束一个 running run（标记为 timeout）。

    后台线程若真卡死无法打断（LLM 同步调用），这里只做状态兜底：把 run 标成
    timeout，让 UI 能识别并允许后续"恢复重跑"（开新线程）。返回更新后的 run。
    """
    run = get_run(run_id)
    if run is None:
        return None
    if run.get("status") == RUN_STATUS_RUNNING:
        update_run(run_id, {"status": RUN_STATUS_TIMEOUT, "error": "已被手动停止"})
    return get_run(run_id)


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
    with _RUN_LOCK:
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
    with _RUN_LOCK:
        data = get_run(run_id)
        if data is None:
            return None
        data.update(updates)
        data["updated_at"] = time.time()
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def add_step(run_id: str, agent_id: str, step_type: str) -> dict | None:
    """Add a step to a run, return the step."""
    with _RUN_LOCK:
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
    with _RUN_LOCK:
        run = get_run(run_id)
        if run is None:
            return None
        for step in run["steps"]:
            if step.get("step_id") == step_id:
                step.update(updates)
                break
        update_run(run_id, {"steps": run["steps"]})
    return run


def run_team(team_id: str, user_input: str, simulate: bool = False) -> dict:
    """Execute a team workflow.

    Returns immediately with a ``running`` run record; real execution continues
    in a background thread (each member step calls the real LLM via
    :mod:`team_worker`). Poll ``get_run`` to observe progress.

    ``simulate=True`` keeps the old sleep-based fake execution (useful for tests
    or environments without a configured LLM).
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
    if mode not in ("sequential", "parallel", "manager"):
        update_run(run_id, {"status": RUN_STATUS_FAILED, "error": f"Unknown mode: {mode}"})
        return get_run(run_id) or run

    # Real execution in a detached background thread so the HTTP handler returns
    # immediately with the run_id while steps fill in as they execute.
    def _background() -> None:
        try:
            _execute_real(run_id, team, user_input, simulate)
        except Exception as exc:  # noqa: BLE001 — 兜底标记失败
            logger.exception("team run %s crashed", run_id)
            with contextlib.suppress(Exception):
                update_run(run_id, {"status": RUN_STATUS_FAILED, "error": str(exc)})

    threading.Thread(target=_background, name=f"team-run-{run_id}", daemon=True).start()
    return get_run(run_id) or run


def rerun_run(run_id: str, simulate: bool = False) -> dict | None:
    """Re-execute an existing (failed/timeout) run in place.

    Loads the stored run's team + user_input, clears its old steps, resets
    status to ``running``, and drives the real workflow again in a background
    thread. Returns the updated run, or ``None`` if the run/team is gone.
    """
    run = get_run(run_id)
    if run is None:
        return None
    team_id = run.get("team_id") or ""
    user_input = run.get("user_input") or ""
    tf = _teams_dir() / f"{team_id}.json"
    if not tf.is_file():
        with contextlib.suppress(Exception):
            update_run(run_id, {"status": RUN_STATUS_FAILED, "error": f"Team '{team_id}' not found"})
        return get_run(run_id)
    team = json.loads(tf.read_text(encoding="utf-8"))
    team["id"] = team_id

    mode = team.get("mode", "sequential")
    if mode not in ("sequential", "parallel", "manager"):
        update_run(run_id, {"status": RUN_STATUS_FAILED, "error": f"Unknown mode: {mode}"})
        return get_run(run_id)

    # 清空旧步骤，重置为 running 后后台重跑
    update_run(run_id, {"status": RUN_STATUS_RUNNING, "error": None, "steps": []})

    def _background() -> None:
        try:
            _execute_real(run_id, team, user_input, simulate)
        except Exception as exc:  # noqa: BLE001
            logger.exception("team rerun %s crashed", run_id)
            with contextlib.suppress(Exception):
                update_run(run_id, {"status": RUN_STATUS_FAILED, "error": str(exc)})

    threading.Thread(target=_background, name=f"team-rerun-{run_id}", daemon=True).start()
    return get_run(run_id)


# ── 真实执行（后台线程内同步驱动） ────────────────────────────────

def _execute_real(run_id: str, team: dict, user_input: str, simulate: bool) -> None:
    """Drive the real (or simulated) team workflow, recording steps as they run."""
    mode = team.get("mode", "sequential")
    members = team.get("members", [])
    error_policy = team.get("error_policy", "stop")
    timeout = team.get("timeout_seconds", 300)
    manager_id = str(team.get("manager_id") or "")

    try:
        if simulate:
            if mode == "sequential":
                _sim_sequential(run_id, members, user_input)
            elif mode == "parallel":
                _sim_parallel(run_id, members, user_input)
            else:
                _sim_manager(run_id, members, user_input, manager_id)
        else:
            if mode == "sequential":
                _real_sequential(run_id, members, user_input, error_policy, timeout)
            elif mode == "parallel":
                _real_parallel(run_id, members, user_input, error_policy, timeout)
            else:
                _real_manager(run_id, members, user_input, error_policy, timeout, manager_id)
        update_run(run_id, {"status": RUN_STATUS_DONE})
    except Exception as exc:  # noqa: BLE001
        logger.exception("team run %s failed", run_id)
        update_run(run_id, {"status": RUN_STATUS_FAILED, "error": str(exc)})


def _member_agent_id(member) -> str:
    if isinstance(member, str):
        return member
    if isinstance(member, dict):
        return str(member.get("id") or member.get("agent_id") or member.get("role") or "")
    return ""


def _member_role_prompt(member) -> str:
    """Role/system prompt for a member (A role-play form), or '' if none."""
    if isinstance(member, dict):
        return str(member.get("system_prompt") or member.get("role_prompt") or "")
    return ""


def _member_error_policy(error_policy: str) -> bool:
    """True when a member failure should abort the whole run."""
    return error_policy == "stop"


def _real_sequential(run_id: str, members: list, user_input: str, error_policy: str, timeout: int) -> None:
    """Members run one after another; each sees the previous member's output."""
    from codeagent.server.team_worker import run_member_step

    context = user_input
    for member in members:
        agent_id = _member_agent_id(member)
        if not agent_id:
            continue
        role = _member_role_prompt(member)
        step = add_step(run_id, agent_id, "sequential")
        if step is None:
            return
        update_step(run_id, step["step_id"], {"status": STEP_STATUS_RUNNING, "input": context})
        try:
            output = run_member_step(agent_id=agent_id, task=context, role_prompt=role)
            if not output:
                output = f"[成员 {agent_id} 无输出]"
            update_step(run_id, step["step_id"], {"status": STEP_STATUS_DONE, "output": output})
            context = output  # 前一步产出作为下一步输入
        except Exception as exc:
            update_step(run_id, step["step_id"], {"status": STEP_STATUS_FAILED, "output": f"错误: {exc}"})
            if _member_error_policy(error_policy):
                raise


def _real_parallel(run_id: str, members: list, user_input: str, error_policy: str, timeout: int) -> None:
    """All members run concurrently on the same input."""
    import concurrent.futures

    from codeagent.server.team_worker import run_member_step

    def _one(member) -> None:
        agent_id = _member_agent_id(member)
        if not agent_id:
            return
        role = _member_role_prompt(member)
        step = add_step(run_id, agent_id, "parallel")
        if step is None:
            return
        update_step(run_id, step["step_id"], {"status": STEP_STATUS_RUNNING, "input": user_input})
        try:
            output = run_member_step(agent_id=agent_id, task=user_input, role_prompt=role)
            update_step(run_id, step["step_id"], {"status": STEP_STATUS_DONE, "output": output or f"[成员 {agent_id} 无输出]"})
        except Exception as exc:
            update_step(run_id, step["step_id"], {"status": STEP_STATUS_FAILED, "output": f"错误: {exc}"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(members))) as pool:
        futures = [pool.submit(_one, m) for m in members]
        concurrent.futures.wait(futures)


def _real_manager(run_id: str, members: list, user_input: str, error_policy: str, timeout: int, manager_id: str = "") -> None:
    """PM (manager_id or first member) splits the task; workers each execute a piece."""
    from codeagent.server.team_worker import run_member_step

    if not members:
        return
    pm_member = next((m for m in members if _member_agent_id(m) == manager_id), None) if manager_id else None
    pm_agent = _member_agent_id(pm_member) if pm_member else (_member_agent_id(members[0]) if members else "")
    if not pm_member:
        pm_member = members[0] if members else None
    pm_role = _member_role_prompt(pm_member)
    workers = [m for m in members if _member_agent_id(m) != pm_agent]

    # PM step：分析并拆分子任务（真实产出子任务清单）
    pm_step = add_step(run_id, pm_agent, "manager-pm")
    if pm_step is None:
        return
    update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_RUNNING, "input": user_input})
    try:
        pm_output = run_member_step(
            agent_id=pm_agent,
            task=(
                f"你是团队负责人(PM)。请把下面的任务拆成 {max(len(workers), 1)} 个"
                f"明确、独立的子任务，每行一个，直接输出子任务清单，不要多余解释。\n\n任务: {user_input}"
            ),
            role_prompt=pm_role,
        )
    except Exception as exc:
        update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_FAILED, "output": f"错误: {exc}"})
        if _member_error_policy(error_policy):
            raise
        return
    update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_DONE, "output": pm_output})

    # 无 worker 可派发：PM 已完成分析，run 到此结束（正常 done）。
    if not workers:
        return

    # Worker steps：把 PM 产出的子任务分给各 worker
    subtasks = _split_subtasks(pm_output, len(workers))
    for i, worker in enumerate(workers):
        wid = _member_agent_id(worker)
        wrole = _member_role_prompt(worker)
        sub = subtasks[i] if i < len(subtasks) else f"子任务 {i+1}（承接 PM 拆解）"
        w_step = add_step(run_id, wid, "manager-worker")
        if w_step is None:
            return
        update_step(run_id, w_step["step_id"], {
            "status": STEP_STATUS_RUNNING,
            "input": sub,
        })
        try:
            w_output = run_member_step(agent_id=wid, task=sub, role_prompt=wrole)
            update_step(run_id, w_step["step_id"], {"status": STEP_STATUS_DONE, "output": w_output or f"[成员 {wid} 无输出]"})
        except Exception as exc:
            update_step(run_id, w_step["step_id"], {"status": STEP_STATUS_FAILED, "output": f"错误: {exc}"})
            if _member_error_policy(error_policy):
                raise


def _split_subtasks(pm_output: str, n: int) -> list[str]:
    """Split PM's subtask list output into up to n subtasks (line based, tolerant)."""
    lines = [ln.strip() for ln in (pm_output or "").splitlines() if ln.strip()]
    # 去掉行首序号/项目符号
    cleaned = []
    for ln in lines:
        for prefix in ("- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ", "8. ", "9. ", "0. ", "①", "②", "③", "④", "⑤"):
            if ln.startswith(prefix):
                ln = ln[len(prefix):].strip()
        if ln:
            cleaned.append(ln)
    if not cleaned:
        return []
    n = max(1, n)  # 防御：n<=0（无 worker）时退化为单桶
    # 若行数不足 n，按行返回；否则均匀归并到 n 份（不丢行）
    if len(cleaned) <= n:
        return cleaned + [f"子任务 {i+1}" for i in range(len(cleaned), n)]
    # 均匀分桶：base 每桶数量 + 前 rem 桶多一个，保证所有行都分到
    base, rem = divmod(len(cleaned), n)
    parts: list[str] = []
    idx = 0
    for b in range(n):
        size = base + (1 if b < rem else 0)
        parts.append("\n".join(cleaned[idx:idx + size]))
        idx += size
    return parts


# ── 模拟执行（simulate=True，测试/无 LLM 回退） ───────────────────

def _sim_sequential(run_id: str, members: list, user_input: str) -> None:
    context = user_input
    for member in members:
        agent_id = _member_agent_id(member)
        if not agent_id:
            continue
        step = add_step(run_id, agent_id, "sequential")
        if step is None:
            return
        update_step(run_id, step["step_id"], {"status": STEP_STATUS_RUNNING, "input": context})
        time.sleep(0.05)
        output = f"[模拟] Agent '{agent_id}' 处理完成:\n收到: {context[:100]}..."
        update_step(run_id, step["step_id"], {"status": STEP_STATUS_DONE, "output": output})
        context = output


def _sim_parallel(run_id: str, members: list, user_input: str) -> None:
    import concurrent.futures

    def _run_one(agent_id: str) -> None:
        step = add_step(run_id, agent_id, "parallel")
        sid = step["step_id"] if step else ""
        update_step(run_id, sid, {"status": STEP_STATUS_RUNNING, "input": user_input})
        time.sleep(0.05)
        update_step(run_id, sid, {"status": STEP_STATUS_DONE, "output": f"[模拟] Agent '{agent_id}' 并行处理完成"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(members)) as pool:
        futures = [pool.submit(_run_one, _member_agent_id(m)) for m in members]
        concurrent.futures.wait(futures)


def _sim_manager(run_id: str, members: list, user_input: str, manager_id: str = "") -> None:
    if not members:
        return
    member_ids = [_member_agent_id(m) for m in members]
    pm_id = manager_id if manager_id and manager_id in member_ids else _member_agent_id(members[0])
    workers = [m for m in members if _member_agent_id(m) != pm_id]

    pm_step = add_step(run_id, pm_id, "manager-pm")
    if pm_step is None:
        return
    update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_RUNNING, "input": user_input})
    time.sleep(0.05)
    pm_output = f"[模拟] PM '{pm_id}' 将任务拆分为 {max(len(workers), 1)} 个子任务"
    update_step(run_id, pm_step["step_id"], {"status": STEP_STATUS_DONE, "output": pm_output})

    for i, worker in enumerate(workers):
        wid = _member_agent_id(worker)
        w_step = add_step(run_id, wid, "manager-worker")
        if w_step is None:
            return
        update_step(run_id, w_step["step_id"], {
            "status": STEP_STATUS_RUNNING,
            "input": f"子任务 {i+1}: {user_input[:80]}..."
        })
        time.sleep(0.05)
        update_step(run_id, w_step["step_id"], {"status": STEP_STATUS_DONE, "output": f"[模拟] Worker '{wid}' 完成子任务 {i+1}"})


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
