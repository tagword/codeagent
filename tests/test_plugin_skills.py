"""Plugin skill appendices (seed.config_plane)."""

from __future__ import annotations

import json
from pathlib import Path

from seed.core.config_plane import _plugin_skill_appendices


def test_plugin_skills_respect_toggle(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config"
    skills = cfg / "skills"
    skills.mkdir(parents=True)
    (skills / "alpha.md").write_text("Alpha body", encoding="utf-8")
    (skills / "beta.md").write_text("Beta body", encoding="utf-8")
    (cfg / "codeagent.plugins.json").write_text(
        json.dumps({"plugins": {"alpha": True, "beta": False}}),
        encoding="utf-8",
    )
    chunks = _plugin_skill_appendices(cfg, tmp_path)
    text = "\n".join(chunks)
    assert "Alpha body" in text
    assert "Beta body" not in text


def test_plugin_skills_all_enabled_when_no_toggle_file(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    skills = cfg / "skills"
    skills.mkdir(parents=True)
    (skills / "only.md").write_text("Only one", encoding="utf-8")
    chunks = _plugin_skill_appendices(cfg, tmp_path)
    assert any("Only one" in c for c in chunks)
