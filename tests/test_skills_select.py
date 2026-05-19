"""Dynamic skill selection."""

from __future__ import annotations

import json
from pathlib import Path

from codeagent.skills.select import (
    build_selected_skills_appendix,
    list_agent_skill_entries,
    select_skills,
)


def test_select_skills_respects_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    aid = "default"
    sdir = tmp_path / "agents" / aid / "skills"
    sdir.mkdir(parents=True)
    (sdir / "deploy.md").write_text(
        "# Deploy\n\nUse this when deploying apps to production.",
        encoding="utf-8",
    )
    (sdir / "debug.md").write_text(
        "# Debug\n\nUse when fixing test failures.",
        encoding="utf-8",
    )
    (sdir / "_state.json").write_text(
        json.dumps({"deploy.md": False}),
        encoding="utf-8",
    )
    entries = list_agent_skill_entries(aid)
    names = {e.name for e in entries}
    assert "deploy" not in names
    assert "debug" in names
    picked = select_skills(aid, user_text="fix failing pytest tests", k=2)
    assert picked
    assert picked[0].skill_id == "debug"


def test_build_appendix_contains_skill_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SEED_PROJECT_ROOT", str(tmp_path))
    aid = "default"
    sdir = tmp_path / "agents" / aid / "skills"
    sdir.mkdir(parents=True)
    (sdir / "lint.md").write_text(
        "# Lint\n\nRun ruff before every commit.",
        encoding="utf-8",
    )
    appendix = build_selected_skills_appendix(
        aid, user_text="please run ruff lint before commit", k=1
    )
    assert "Active skills" in appendix
    assert "ruff" in appendix.lower()
