"""prompt_enrichment helpers."""

from __future__ import annotations

import json
from pathlib import Path

from codeagent.runtime.prompt_enrichment import build_skills_suffix, record_chat_turn_diary


def test_build_skills_suffix_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_SKILLS_AUTO", "0")
    assert build_skills_suffix("default", user_text="hello") is None


def test_record_chat_turn_diary_writes_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEAGENT_DIARY", "1")
    record_chat_turn_diary(
        "default",
        user_text="hi",
        reply="hello",
        tools_used=["echo"],
    )
    daily = tmp_path / "agents" / "default" / "memory" / "daily"
    files = list(daily.glob("*.md"))
    assert files
    assert "hi" in files[0].read_text(encoding="utf-8")
