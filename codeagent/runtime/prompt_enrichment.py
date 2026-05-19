"""Runtime prompt enrichment: dynamic skills, fresh system prompt, diary."""

from __future__ import annotations

from typing import Optional

from seed.core.config_plane import build_system_prompt, project_root
from codeagent.core import env as ca_env
from seed.core.env_access import pick_nonempty
import seed.core.env_access as _ea


def fresh_system_prompt(*, agent_id: str | None = None) -> str:
    """
    System prompt for chat: respects Web UI ``config_md_enabled``, plugin skills
    (via ``build_system_prompt``), and optional persona ``memory.md``.
    """
    explicit = pick_nonempty(*_ea.SYSTEM_PROMPT)
    if explicit.strip():
        return explicit.strip()

    from codeagent.core.settings import get_system_prompt_filenames

    base = build_system_prompt(
        base=project_root(),
        filenames=get_system_prompt_filenames(),
    )

    try:
        from seed.core.paths import agent_id_default, agent_persona_memory_path

        aid = (agent_id or "").strip() or agent_id_default()
        p = agent_persona_memory_path(aid)
        if p.is_file():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                max_chars = int(pick_nonempty(*_ea.PERSONA_MEMORY_MAX_CHARS) or "4000")
                max_chars = max(200, min(max_chars, 50_000))
                if len(text) > max_chars:
                    text = text[: max_chars - 20].rstrip() + "\n…[已截断]"
                base = (
                    base.rstrip()
                    + "\n\n---\n"
                    + f"## Persona core memory (`agents/{aid}/persona/memory.md`)\n\n"
                    + text
                    + "\n"
                )
    except Exception:
        pass
    return base


def build_skills_suffix(
    agent_id: str,
    *,
    user_text: str,
    workspace_suffix: str = "",
) -> Optional[str]:
    """Combine workspace hint + dynamically selected agent skills for ``skills_suffix``."""
    parts: list[str] = []
    if workspace_suffix and workspace_suffix.strip():
        parts.append(workspace_suffix.strip())

    if ca_env.env_truthy(ca_env.SKILLS_AUTO, default="1"):
        try:
            from codeagent.skills.select import build_selected_skills_appendix

            appendix = build_selected_skills_appendix(agent_id, user_text=user_text)
            if appendix:
                parts.append(appendix)
        except Exception:
            pass

    if not parts:
        return None
    return "\n".join(parts)


def record_chat_turn_diary(
    agent_id: str,
    *,
    user_text: str,
    reply: str,
    tools_used: list[str] | None = None,
    project_id: str | None = None,
) -> None:
    """Append a short turn summary to the agent daily diary (best-effort)."""
    if ca_env.env_falsy(ca_env.DIARY, default="1"):
        return
    try:
        from codeagent.memory.diary import append_diary_entry, archive_old_diaries

        u = (user_text or "").strip()
        r = (reply or "").strip()
        block = f"**用户**: {u[:500]}\n\n**助手**: {r[:800]}"
        if tools_used:
            block += f"\n\n**工具**: {', '.join(tools_used[:16])}"
        append_diary_entry(agent_id, text=block, project_id=project_id or None)
        keep = ca_env.pick_int(7, ca_env.DIARY_KEEP_DAYS)
        archive_old_diaries(agent_id, keep_days=max(1, min(keep, 60)))
    except Exception:
        pass
