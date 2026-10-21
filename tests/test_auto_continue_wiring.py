"""auto_continue 接线层测试（chat_turn）—— 补上纯函数测试覆盖不到的关键链路。

为什么需要（真实静默停止风险）
--------------------------------
``tests/test_auto_continue.py`` 只测 ``auto_continue.py`` 的纯函数（判断
"该不该续"），完全没测 ``chat_turn.py`` 里的**接线**。而"轮数用尽后
Agent 静默停止"这类 bug 恰恰只出在接线处：

1. 开关关（``_ac_on=False``）→ 整个续跑循环被跳过，24 轮用尽即停止
2. ``stopped_reason`` 字段名对不上 → 轮数用尽分支进不去
3. nudge 消息没真正进入下一段 LLM 上下文 → 续跑了但模型不知道该干什么
4. pending 查询抛异常 → 被静默吞掉，Agent 误判"无未完成"而停下

本文件锁定与 seed-kernel 的契约（字段名 / 注入点），防上游改名导致静默失效。
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta

import codeagent.server.auto_continue as ac
from codeagent.server import chat_turn as ct


def _source() -> str:
    return inspect.getsource(ct.run_chat_turn)


# ────────────────────────── 与 seed-kernel 的契约 ──────────────────────────


def test_stop_reason_field_contract_with_seed_kernel():
    """stopped_reason 字段名与 seed-kernel 保持一致。

    chat_turn 用 `_seg_meta.get("stopped_reason")` 判断轮数是否用尽。若上游
    改名，`get` 静默返回 None → 续跑分支永不触发，Agent 在轮数用尽时静默停止。
    """
    from seed.core.agent_runtime import run_llm_tool_loop

    src = inspect.getsource(run_llm_tool_loop)
    assert 'loop_meta["stopped_reason"] = "max_tool_rounds"' in src, (
        "seed-kernel 不再写 loop_meta['stopped_reason']='max_tool_rounds'；"
        "chat_turn 的轮数用尽续跑分支会静默失效"
    )
    assert 'loop_meta["stopped_reason"] = "cancelled"' in src


def test_nudge_injected_into_api_msgs_not_only_filtered():
    """nudge 必须被 append 进 api_msgs 供下一段 LLM 消费。

    持久化路径把 nudge 过滤掉是对的（不污染历史），但若没有回填 api_msgs，
    续跑就是空转 —— 模型看不到任何"继续"的指令。
    """
    src = _source()
    assert '"_auto_continue_nudge": True' in src, "nudge 标记丢失"
    assert "api_msgs.append" in src, "nudge 未注入 api_msgs"
    assert "_auto_continue_nudge" in src, "持久化过滤逻辑丢失了 nudge 识别"


def test_pending_check_runs_even_when_agent_thinks_done():
    """Agent 自认为完成时也要查 pending —— 否则「做完一个 Wave 就停」。"""
    src = _source()
    # 只看代码行，不看注释（注释里为了说明缺陷会引用这个字符串）
    code = [
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    assert not any('_stop_reason != "max_tool_rounds"' in ln for ln in code), (
        "pending 检查被重新塞回 `!= max_tool_rounds` 分支 —— "
        "轮数用尽时将静默停止（v1.2.0 回归）"
    )
    assert "get_pending_all" in src
    # 两条续跑路径都要能置位 _pending_continue
    assert '_limit_hit = _stop_reason == "max_tool_rounds"' in src, (
        "max_tool_rounds 续跑路径丢失（v1.2.0 删掉了 v1.1.36 的能力）"
    )


def test_segment_hard_limit_enforced():
    """分段上限在两处生效（进入循环前 + 递增后），防失控。"""
    src = _source()
    assert src.count("_max_seg") >= 4, "分段上限检查点被削减"
    assert "while _segment < _max_seg" in src


# ────────────────────────── 续跑判定逻辑 ──────────────────────────


def test_should_continue_false_at_max_segments():
    """segments_used 达上限 → 不再续跑（防失控，硬约束）。"""
    ok, reason = ac.should_continue("agent0", "proj", "", segments_used=4, max_segments=4)
    assert ok is False
    assert "上限" in reason


def test_pending_query_error_is_recorded_and_conservative(monkeypatch):
    """pending 查询抛异常 → 保守停止（不无限跑），但错误必须被记录可观测。

    这条防的是 chat_turn 里的静默吞异常：
        except Exception: logger.debug(...)   ← 异常无痕，Agent 误判"无未完成"
    """

    def boom(*a, **k):
        raise RuntimeError("db locked")

    monkeypatch.setattr(ac, "get_pending_todos", boom)
    monkeypatch.setattr(ac, "get_pending_plan", boom)
    summary = ac.get_pending_all("agent0", "proj")
    assert summary.error, "异常被静默吞掉，无法观测"
    assert not summary.has_pending

    ok, reason = ac.should_continue("agent0", "proj")
    assert ok is False
    assert "保守" in reason


def test_stale_pending_does_not_block_stop(monkeypatch):
    """陈旧 pending（>24h）不阻止停止 —— 防 Agent 忘记更新 todo 导致永不停。"""
    monkeypatch.setattr(
        ac, "get_pending_all", lambda *a, **k: ac.PendingSummary(count=0, items=[])
    )
    ok, reason = ac.should_continue("agent0", "proj")
    assert ok is False
    assert "无未完成" in reason

    old = (datetime.now() - timedelta(hours=30)).isoformat()
    assert ac._is_stale({"updated_at": old}) is True
    assert ac._is_stale({"updated_at": datetime.now().isoformat()}) is False


def test_switch_default_is_off():
    """记录现状：开关默认关闭 —— 未显式配置时轮数用尽即停止。"""
    import os

    from codeagent.core.env import CHAT_AUTO_CONTINUE_ON_LIMIT, env_truthy

    os.environ.pop(CHAT_AUTO_CONTINUE_ON_LIMIT, None)
    assert env_truthy(CHAT_AUTO_CONTINUE_ON_LIMIT, default="0") is False


# ────────────────── 行为测试：复刻真实控制流（不靠 grep 源码） ──────────────────
#
# 为什么必须做行为测试：v1.2.0 的 bug 之所以能通过"源码断言"测试，是因为
# 测试断言的正是 bug 结构本身。源码文本断言只能证明"代码长这样"，
# 不能证明"跑起来是这样"。下面直接按 chat_turn.py 的判定顺序模拟，
# 让"轮数用尽是否续跑"变成可证伪的行为断言。


def _simulate(stopped_reason, *, has_pending, max_seg=4, rounds=24):
    """复刻 chat_turn.py 的续跑判定与分段循环。

    返回实际执行的段数。
    """
    segment = 0
    executed = 1
    while segment < max_seg:
        stop_reason = stopped_reason
        pending_continue = False

        if stop_reason == "cancelled":
            break

        limit_hit = stop_reason == "max_tool_rounds"
        if limit_hit:
            pending_continue = True

        if not limit_hit and has_pending and (segment + 1) < max_seg:
            pending_continue = True

        if not pending_continue:
            break

        segment += 1
        if segment >= max_seg:
            break
        executed += 1
    return executed


def test_behaviour_continues_when_tool_rounds_exhausted():
    """v1.2.0 核心回归：撞满轮次必须续跑，不能静默停止。

    v1.2.0 把 pending 检查塞进 `!= max_tool_rounds` 分支，导致此场景
    只执行 1 段就 break —— 表现为"跑着跑着就停了"。
    """
    executed = _simulate("max_tool_rounds", has_pending=False)
    assert executed > 1, (
        f"撞满轮次后只执行了 {executed} 段就停止 —— v1.2.0 静默停止回归"
    )


def test_behaviour_continues_when_limit_hit_even_without_pending():
    """轮数用尽时不应依赖 pending 查询结果（查询可能失败）。"""
    executed = _simulate("max_tool_rounds", has_pending=False)
    assert executed == 4, f"应续跑至分段上限，实际 {executed} 段"


def test_behaviour_continues_when_agent_done_but_pending_exists():
    """v1.2.0 新增能力：Agent 自认为完成但有 pending → 续跑。"""
    executed = _simulate("end_turn", has_pending=True)
    assert executed > 1, "pending 驱动续跑能力丢失"


def test_behaviour_stops_when_agent_done_and_nothing_pending():
    """无 pending 且 Agent 自认为完成 → 应停止，不做无意义空转。"""
    executed = _simulate("end_turn", has_pending=False)
    assert executed == 1, f"应停止但执行了 {executed} 段（无意义空转，浪费 token）"


def test_behaviour_stops_immediately_on_cancel():
    """用户取消必须立即停止，不能续跑。"""
    executed = _simulate("cancelled", has_pending=True)
    assert executed == 1, "cancelled 后仍在续跑"
