"""codeagent.runtime.task_split 单元测试。

覆盖 auto_split_enabled 与 split_user_tasks 的启发式拆分规则：
--- 分隔 / 编号列表(≥2) / 单任务 / 空 / 不误拆。
"""
import pytest

from codeagent.core import env as ca_env
from codeagent.runtime import task_split as ts


# ---------- auto_split_enabled ----------
def test_auto_split_explicit_true():
    assert ts.auto_split_enabled(explicit=True) is True
    assert ts.auto_split_enabled(explicit=False) is False


def test_auto_split_explicit_none_uses_env(monkeypatch):
    monkeypatch.delenv(ca_env.ORCHESTRATOR_AUTO_SPLIT, raising=False)
    assert ts.auto_split_enabled() is False  # 默认 "0"


def test_auto_split_env_true(monkeypatch):
    monkeypatch.setenv(ca_env.ORCHESTRATOR_AUTO_SPLIT, "1")
    assert ts.auto_split_enabled() is True


# ---------- split_user_tasks ----------
def test_split_empty():
    assert ts.split_user_tasks("") == []
    assert ts.split_user_tasks("   ") == []


def test_split_single_task():
    assert ts.split_user_tasks("只做这一件事") == ["只做这一件事"]


def test_split_single_task_strips():
    assert ts.split_user_tasks("  只做这一件事  ") == ["只做这一件事"]


def test_split_dash_separator():
    assert ts.split_user_tasks("任务A\n---\n任务B\n---\n任务C") == ["任务A", "任务B", "任务C"]


def test_split_dash_separator_with_spaces():
    # 顶格 --- 才被识别为分隔符（markdown 分隔线标准写法）
    assert ts.split_user_tasks("A\n---\nB") == ["A", "B"]


def test_split_dash_with_leading_space_not_separator():
    # 带前导空格的 --- 不被识别（当前行为：需顶格）
    assert ts.split_user_tasks("A\n --- \nB") == ["A\n --- \nB"]


def test_split_numbered_list():
    assert ts.split_user_tasks("1. 第一\n2. 第二\n3. 第三") == ["第一", "第二", "第三"]


def test_split_numbered_with_paren():
    assert ts.split_user_tasks("1) 甲\n2) 乙") == ["甲", "乙"]


def test_split_single_numbered_not_split():
    # 单个编号 → 不拆，返回整段
    assert ts.split_user_tasks("1. 只做这一件事") == ["1. 只做这一件事"]


def test_split_plain_text_with_numbers_not_split():
    # 普通文本含数字 → 不误拆
    assert ts.split_user_tasks("我 2024 年做了 3 个任务，质量都不错") == [
        "我 2024 年做了 3 个任务，质量都不错"
    ]


def test_split_dash_takes_priority_over_numbers():
    # --- 规则优先于编号
    text = "1. 甲\n---\n2. 乙\n---\n3. 丙"
    parts = ts.split_user_tasks(text)
    assert len(parts) == 3


def test_split_indented_numbered():
    assert ts.split_user_tasks("  1. 甲\n  2. 乙") == ["甲", "乙"]
