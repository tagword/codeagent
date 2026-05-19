"""Heuristic task splitting for multi-worker orchestration."""

from __future__ import annotations

import re

from codeagent.core import env as ca_env


def auto_split_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return ca_env.env_truthy(ca_env.ORCHESTRATOR_AUTO_SPLIT, default="0")


def split_user_tasks(user_text: str) -> list[str]:
    """
    Split a user message into subtasks.

    Rules (first match wins):
    1. ``---`` on its own line
    2. Numbered lines ``1.`` ``2.`` (at least 2 items)
    3. Otherwise single task
    """
    text = (user_text or "").strip()
    if not text:
        return []

    if re.search(r"(?m)^---\s*$", text):
        parts = [p.strip() for p in re.split(r"(?m)^---\s*$", text) if p.strip()]
        if len(parts) > 1:
            return parts

    numbered = re.findall(r"(?m)^\s*\d+[.)]\s+(.+)$", text)
    if len(numbered) >= 2:
        return [p.strip() for p in numbered if p.strip()]

    return [text]
