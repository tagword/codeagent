from __future__ import annotations

from pathlib import Path

import pytest

from codeagent.runtime.compact_state import inject_state_into_system


def test_inject_state_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "state.md"
    state_file.write_text("项目进度：首页已完成\n", encoding="utf-8")

    def _read_state(agent_id: str) -> str:
        return state_file.read_text(encoding="utf-8")

    monkeypatch.setattr("codeagent.core.paths.read_state_file", _read_state)

    api_msgs = [{"role": "system", "content": "system prompt"}]
    inject_state_into_system(api_msgs, "default")

    content = api_msgs[0]["content"]
    assert "<<<STATE>>>" in content
    assert "首页已完成" in content
    assert "<<<END_STATE>>>" in content


def test_inject_state_replaces_previous_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_file = tmp_path / "state.md"
    state_file.write_text("new state\n", encoding="utf-8")

    monkeypatch.setattr(
        "codeagent.core.paths.read_state_file",
        lambda agent_id: state_file.read_text(encoding="utf-8"),
    )

    api_msgs = [
        {
            "role": "system",
            "content": "base\n\n<<<STATE>>>\n-old-\n<<<END_STATE>>>",
        }
    ]
    inject_state_into_system(api_msgs, "default")

    content = api_msgs[0]["content"]
    assert "-old-" not in content
    assert "new state" in content
