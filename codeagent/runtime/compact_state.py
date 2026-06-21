"""Inject project state into system prompt after compact."""

from __future__ import annotations

import re
from typing import Any

_STATE_BLOCK_RE = re.compile(
    r"\n+<<<STATE>>>\n.*?\n<<<END_STATE>>>\n?",
    re.DOTALL,
)


def inject_state_into_system(
    api_msgs: list[dict[str, Any]],
    agent_id: str,
) -> None:
    """After compact, inject ``state.md`` into ``api_msgs[0]`` system prompt."""
    if not api_msgs:
        return

    try:
        from codeagent.core.paths import read_state_file
    except Exception:
        return

    state_text = read_state_file(agent_id)
    if not state_text:
        return

    sys_msg = api_msgs[0]
    content = str(sys_msg.get("content") or "")
    content = _STATE_BLOCK_RE.sub("\n", content).strip()
    sys_msg["content"] = (
        content
        + "\n\n<<<STATE>>>\n"
        "## 当前项目状态\n\n"
        f"{state_text}\n"
        "<<<END_STATE>>>"
    )
