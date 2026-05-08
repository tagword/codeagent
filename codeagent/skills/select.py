"""Agent-private skills selection via routing scorer (strategy B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from codeagent.core.paths import agent_skills_dir
from seed.models import CommandEntry
from seed.routing import score_entries


@dataclass
class SelectedSkill:
    skill_id: str
    path: Path
    description: str


def _skill_description_from_file(path: Path, *, max_lines: int = 10, max_chars: int = 400) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = raw.splitlines()
    take = "\n".join(lines[: max(1, int(max_lines))]).strip()
    if len(take) > max_chars:
        take = take[: max_chars - 1].rstrip() + "…"
    return take


def list_agent_skill_entries(agent_id: str) -> List[CommandEntry]:
    d = agent_skills_dir(agent_id)
    if not d.is_dir():
        return []
    out: List[CommandEntry] = []
    for p in sorted(d.glob("*.md")):
        sid = p.stem.strip()
        if not sid:
            continue
        desc = _skill_description_from_file(p)
        out.append(CommandEntry(sid, desc, "skill"))
    return out


def select_skills(agent_id: str, *, user_text: str, k: int = 3) -> List[SelectedSkill]:
    entries = list_agent_skill_entries(agent_id)
    if not entries:
        return []
    picked = score_entries(user_text or "", entries, limit=max(1, int(k)))
    d = agent_skills_dir(agent_id)
    out: List[SelectedSkill] = []
    for e in picked[: max(1, int(k))]:
        path = (d / f"{e.name}.md").resolve()
        out.append(SelectedSkill(skill_id=e.name, path=path, description=e.description or ""))
    return out


def read_skill_text(skill: SelectedSkill, *, max_chars: int = 8000) -> str:
    try:
        raw = skill.path.read_text(encoding="utf-8")
    except OSError:
        return ""
    t = raw.strip()
    if len(t) > max_chars:
        t = t[: max_chars - 24].rstrip() + "\n…[skill 内容已截断]"
    return t

