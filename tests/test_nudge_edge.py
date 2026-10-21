"""codeagent.server._auto_continue_nudge 边界单元测试。

覆盖 failure_streak 非整数值容错、recent_errors 各种形态。
（修复：failure_streak 非法字符串不再抛 ValueError）
"""
from codeagent.server import _auto_continue_nudge


def test_streak_missing_ok():
    out = _auto_continue_nudge({"failure_domain": "bash", "recent_errors": []})
    assert "策略切换触发" in out
    assert "0 次" in out


def test_streak_non_integer_no_crash():
    # 修复点：非法字符串不再抛 ValueError
    out = _auto_continue_nudge(
        {"failure_domain": "bash", "failure_streak": "abc", "recent_errors": []}
    )
    assert "策略切换触发" in out


def test_streak_numeric_string_ok():
    out = _auto_continue_nudge(
        {"failure_domain": "bash", "failure_streak": "5", "recent_errors": []}
    )
    assert "5 次" in out


def test_streak_none_ok():
    out = _auto_continue_nudge(
        {"failure_domain": "bash", "failure_streak": None, "recent_errors": []}
    )
    assert "策略切换触发" in out


def test_recent_errors_not_list_ok():
    # recent_errors 是 dict（非 list）→ 忽略，不崩
    out = _auto_continue_nudge(
        {"failure_domain": "bash", "failure_streak": 2, "recent_errors": {"tool": "x"}}
    )
    assert "策略切换触发" in out


def test_recent_errors_contains_non_dict_skipped():
    out = _auto_continue_nudge(
        {
            "failure_domain": "bash",
            "failure_streak": 2,
            "recent_errors": ["just-string", {"tool": "bash", "error": "real"}],
        }
    )
    assert "real" in out
    assert "just-string" not in out


def test_only_last_three_errors_kept():
    errors = [{"tool": f"t{i}", "error": f"e{i}"} for i in range(5)]
    out = _auto_continue_nudge(
        {"failure_domain": "bash", "failure_streak": 5, "recent_errors": errors}
    )
    # 只保留最后 3 个（t2/t3/t4）
    assert "t2" in out
    assert "t4" in out
    assert "t0" not in out
    assert "t1" not in out


def test_error_missing_fields_ok():
    out = _auto_continue_nudge(
        {"failure_domain": "bash", "failure_streak": 2, "recent_errors": [{"tool": "x"}]}
    )
    assert "策略切换触发" in out
