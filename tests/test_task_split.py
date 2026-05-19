"""Task splitting heuristics."""

from __future__ import annotations

from codeagent.runtime.task_split import split_user_tasks


def test_split_on_dashes() -> None:
    text = "first part\n\n---\n\nsecond part"
    parts = split_user_tasks(text)
    assert len(parts) == 2
    assert "first" in parts[0]
    assert "second" in parts[1]


def test_split_numbered() -> None:
    text = "1. Do alpha\n2. Do beta\n"
    parts = split_user_tasks(text)
    assert len(parts) == 2
