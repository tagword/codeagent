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


def _read_skills_state(state_path: Path) -> dict[str, bool]:
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


def _scan_one_skills_dir(directory: Path, state: dict[str, bool], seen: set[str]) -> list[CommandEntry]:
    """Scan one skills directory for both flat .md and skills/<name>/SKILL.md formats.

    Args:
        directory: The skills directory to scan.
        state: Enable/disable map keyed by filename (e.g. ``"deploy.md"``).
        seen: Set of skill_ids already found (to deduplicate).

    Returns:
        List of new CommandEntry items not already in *seen*.
    """
    out: list[CommandEntry] = []
    if not directory.is_dir():
        return out

    # 1st pass: flat .md files
    for p in sorted(directory.glob("*.md")):
        if p.name.startswith(".") or p.name == "_state.json":
            continue
        sid = p.stem.strip()
        if not sid or sid in seen:
            continue
        if not _skill_enabled(state, p.name):
            continue
        desc = _skill_description_from_file(p)
        out.append(CommandEntry(sid, desc, "skill"))
        seen.add(sid)

    # 2nd pass: directory format skills/<name>/SKILL.md
    for p in sorted(directory.glob("*/SKILL.md")):
        dirname = p.parent.name
        if dirname.startswith("."):
            continue
        sid = dirname.strip()
        if not sid or sid in seen:
            continue
        state_key = f"{sid}.md"
        if not _skill_enabled(state, state_key):
            continue
        desc = _skill_description_from_file(p)
        out.append(CommandEntry(sid, desc, "skill"))
        seen.add(sid)

    return out


def _project_skills_dir(agent_id: str, project_path: Path) -> Path:
    """Return ``<project>/.codeagent/{agent_id}/skills/``."""
    return project_path.resolve() / ".codeagent" / agent_id / "skills"


def list_agent_skill_entries(
    agent_id: str,
    project_path: str | Path | None = None,
) -> list[CommandEntry]:
    """List all enabled skill entries for *agent_id*.

    When *project_path* is provided, project-level skills are scanned first
    (higher priority), then agent-level skills, then global ``config/skills/``.
    """
    state_path = agent_skills_dir(agent_id) / "_state.json"
    state = _read_skills_state(state_path)
    out: list[CommandEntry] = []
    seen: set[str] = set()

    # 1. Project-level skills (<project>/.codeagent/{agent_id}/skills/)
    if project_path:
        pdir = _project_skills_dir(agent_id, Path(project_path))
        if pdir.is_dir():
            pstate_path = pdir / "_state.json"
            pstate = _read_skills_state(pstate_path)
            out.extend(_scan_one_skills_dir(pdir, pstate, seen))

    # 2. Agent-level skills
    d = agent_skills_dir(agent_id)
    if d.is_dir():
        out.extend(_scan_one_skills_dir(d, state, seen))

    # 3. Global config/skills/*.md (same enable map keyed by filename)
    gdir = project_root() / "config" / "skills"
    if gdir.is_dir():
        gseen = {e.name for e in out}
        for p in sorted(gdir.glob("*.md")):
            if p.name.startswith(".") or p.stem in gseen:
                continue
            if not _skill_enabled(state, p.name):
                continue
            sid = p.stem.strip()
            if not sid:
                continue
            desc = _skill_description_from_file(p)
            out.append(CommandEntry(sid, desc, "skill"))

    return out


def _resolve_skill_path(
    agent_id: str,
    skill_id: str,
    project_path: str | Path | None = None,
) -> Path:
    """Resolve skill file path, checking project → agent → global in order."""
    # Project-level: skills/<name>/SKILL.md or <name>.md
    if project_path:
        pdir = _project_skills_dir(agent_id, Path(project_path))
        dirfmt = pdir / skill_id / "SKILL.md"
        if dirfmt.is_file():
            return dirfmt.resolve()
        flat = pdir / f"{skill_id}.md"
        if flat.is_file():
            return flat.resolve()

    # Agent-level
    adir = agent_skills_dir(agent_id)
    dirfmt = adir / skill_id / "SKILL.md"
    if dirfmt.is_file():
        return dirfmt.resolve()
    flat = adir / f"{skill_id}.md"
    if flat.is_file():
        return flat.resolve()

    # Global fallback
    global_path = project_root() / "config" / "skills" / f"{skill_id}.md"
    return global_path.resolve()


def select_skills(
    agent_id: str,
    *,
    user_text: str,
    k: int = 3,
    project_path: str | Path | None = None,
) -> list[SelectedSkill]:
    entries = list_agent_skill_entries(agent_id, project_path=project_path)
    if not entries:
        return []
    top_k = max(1, int(k))
    picked = score_entries(user_text or "", entries, limit=top_k)
    out: list[SelectedSkill] = []
    for e in picked[:top_k]:
        path = _resolve_skill_path(agent_id, e.name, project_path=project_path)
        if not path.is_file():
            continue
        out.append(
            SelectedSkill(skill_id=e.name, path=path, description=e.description or "")
        )
    return out


def build_selected_skills_appendix(
    agent_id: str,
    *,
    user_text: str,
    k: int | None = None,
    project_path: str | Path | None = None,
) -> str:
    """Markdown block appended to system prompt for this turn (empty if none)."""
    if k is None:
        from codeagent.core import env as ca_env

        k = ca_env.pick_int(3, ca_env.SKILLS_TOP_K)
    picked = select_skills(
        agent_id, user_text=user_text, k=k, project_path=project_path,
    )
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
