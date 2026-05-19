"""Agent daily diary."""

from __future__ import annotations

from pathlib import Path

from codeagent.memory.diary import append_diary_entry, daily_path


def test_append_diary_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    aid = "default"
    p = append_diary_entry(aid, text="First turn summary")
    assert p.is_file()
    body = p.read_text(encoding="utf-8")
    assert "First turn summary" in body
    assert daily_path(aid).name.endswith(".md")
