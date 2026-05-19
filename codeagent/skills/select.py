"""Agent-private skills selection via routing scorer (strategy B)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from codeagent.core.paths import agent_skills_dir
from seed.core.config_plane import project_root
from seed.core.routing import score_entries
from seed.models import CommandEntry


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


def _read_skills_state(agent_id: str) -> dict[str, bool]:
    state_path = agent_skills_dir(agent_id) / "_state.json"
    if not state_path.is_file():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): bool(v) for k, v in raw.items()}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _skill_enabled(state: dict[str, bool], filename: str) -> bool:
    return state.get(filename, True)


def list_agent_skill_entries(agent_id: str) -> list[CommandEntry]:
    d = agent_skills_dir(agent_id)
    state = _read_skills_state(agent_id)
    out: list[CommandEntry] = []
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            if p.name.startswith("."):
                continue
            if not _skill_enabled(state, p.name):
                continue
            sid = p.stem.strip()
            if not sid:
                continue
            desc = _skill_description_from_file(p)
            out.append(CommandEntry(sid, desc, "skill"))
    # Global config/skills/*.md (same enable map keyed by filename)
    gdir = project_root() / "config" / "skills"
    if gdir.is_dir():
        seen = {e.name for e in out}
        for p in sorted(gdir.glob("*.md")):
            if p.name.startswith(".") or p.stem in seen:
                continue
            if not _skill_enabled(state, p.name):
                continue
            sid = p.stem.strip()
            if not sid:
                continue
            desc = _skill_description_from_file(p)
            out.append(CommandEntry(sid, desc, "skill"))
    return out


def _resolve_skill_path(agent_id: str, skill_id: str) -> Path:
    agent_path = agent_skills_dir(agent_id) / f"{skill_id}.md"
    if agent_path.is_file():
        return agent_path.resolve()
    global_path = project_root() / "config" / "skills" / f"{skill_id}.md"
    return global_path.resolve()


def select_skills(agent_id: str, *, user_text: str, k: int = 3) -> list[SelectedSkill]:
    entries = list_agent_skill_entries(agent_id)
    if not entries:
        return []
    top_k = max(1, int(k))
    picked = score_entries(user_text or "", entries, limit=top_k)
    out: list[SelectedSkill] = []
    for e in picked[:top_k]:
        path = _resolve_skill_path(agent_id, e.name)
        if not path.is_file():
            continue
        out.append(
            SelectedSkill(skill_id=e.name, path=path, description=e.description or "")
        )
    return out


def build_selected_skills_appendix(
    agent_id: str, *, user_text: str, k: int | None = None
) -> str:
    """Markdown block appended to system prompt for this turn (empty if none)."""
    if k is None:
        from codeagent.core import env as ca_env

        k = ca_env.pick_int(3, ca_env.SKILLS_TOP_K)
    picked = select_skills(agent_id, user_text=user_text, k=k)
    if not picked:
        return ""
    parts = [
        "\n\n---\n",
        "## Active skills (matched this turn)\n",
        "Follow these skill instructions when relevant.\n",
    ]
    for sk in picked:
        body = read_skill_text(sk)
        if not body:
            continue
        parts.append(f"\n### Skill: {sk.skill_id}\n\n{body}\n")
    if len(parts) <= 3:
        return ""
    return "".join(parts)


def read_skill_text(skill: SelectedSkill, *, max_chars: int = 8000) -> str:
    try:
        raw = skill.path.read_text(encoding="utf-8")
    except OSError:
        return ""
    t = raw.strip()
    if len(t) > max_chars:
        t = t[: max_chars - 24].rstrip() + "\n…[skill 内容已截断]"
    return t

