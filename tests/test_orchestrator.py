"""codeagent.runtime.orchestrator 单元测试。

覆盖并行编排的错误处理：异常子任务用原始 index 记录，不覆盖其他任务结果。
（修复：原实现用 len(results) 作 key，异常时可能覆盖已完成任务）
"""
from codeagent.runtime.orchestrator import Orchestrator
from codeagent.runtime.worker import Worker


class FakeImpl:
    """模拟真实 worker impl，可指定哪些任务失败。"""

    def __init__(self, fail_substring=None):
        self.fail_substring = fail_substring

    def run(self, *, session_id, user_text, tools=None, max_tool_rounds=16):
        if self.fail_substring and self.fail_substring in user_text:
            raise RuntimeError(f"boom: {user_text}")
        return f"OK[{user_text}]", {"w": user_text}


def _make_workers(n, fail_substring=None):
    workers = [Worker() for _ in range(n)]
    for wk in workers:
        wk.impl = FakeImpl(fail_substring=fail_substring)
    return workers


def test_parallel_no_workers_raises():
    orch = Orchestrator(workers=[])
    try:
        orch.run(session_id="s", user_text="x")
        assert False, "should raise"
    except RuntimeError:
        pass


def test_parallel_all_success():
    orch = Orchestrator(workers=_make_workers(2), parallel=True)
    reply, meta = orch.run(
        session_id="s", user_text="x",
        metadata={"parallel": True, "subtasks": ["任务0", "任务1"]},
    )
    assert "OK[任务0]" in reply
    assert "OK[任务1]" in reply
    assert meta["orchestrator"]["mode"] == "parallel"
    assert meta["orchestrator"]["tasks"] == 2


def test_parallel_error_uses_original_index_not_overwrite():
    """坏任务在中间，异常应记录到它自己的 index，不覆盖其他已成功任务。"""
    orch = Orchestrator(workers=_make_workers(3, fail_substring="坏"), parallel=True)
    reply, meta = orch.run(
        session_id="s", user_text="x",
        metadata={"parallel": True, "subtasks": ["任务0", "坏任务1", "任务2"]},
    )
    # 任务0 和 任务2 正常
    assert "OK[任务0]" in reply
    assert "OK[任务2]" in reply
    # 坏任务1 显示错误
    assert "[subtask error] boom: 坏任务1" in reply
    # 三个 subtask 都在
    assert "### Subtask 1" in reply
    assert "### Subtask 2" in reply
    assert "### Subtask 3" in reply


def test_parallel_error_on_first_task():
    orch = Orchestrator(workers=_make_workers(2, fail_substring="坏"), parallel=True)
    reply, _ = orch.run(
        session_id="s", user_text="x",
        metadata={"parallel": True, "subtasks": ["坏任务0", "任务1"]},
    )
    assert "[subtask error]" in reply
    assert "OK[任务1]" in reply


def test_single_task_uses_single_mode():
    orch = Orchestrator(workers=_make_workers(2), parallel=True)
    reply, meta = orch.run(session_id="s", user_text="单任务")
    assert meta["orchestrator"]["mode"] == "single"
    assert "OK[单任务]" in reply


def test_sequential_mode():
    orch = Orchestrator(workers=_make_workers(2), parallel=False)
    reply, meta = orch.run(
        session_id="s", user_text="x",
        metadata={"subtasks": ["甲", "乙"]},
    )
    assert meta["orchestrator"]["mode"] == "sequential"
    assert "OK[甲]" in reply
    assert "OK[乙]" in reply
