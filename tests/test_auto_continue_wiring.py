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
    assert 'if _stop_reason != "max_tool_rounds"' in src
    assert "get_pending_all" in src


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
