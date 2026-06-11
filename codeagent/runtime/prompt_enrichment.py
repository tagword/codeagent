"""Runtime prompt enrichment: dynamic skills, fresh system prompt, diary."""

from __future__ import annotations

from typing import Optional  # noqa: UP045

import seed.core.env_access as _ea
from codeagent.core import env as ca_env
from seed.core.config_plane import build_system_prompt, project_root
from seed.core.env_access import pick_nonempty


def _compute_persona_hash(agent_id: str) -> str:
    """Hash of all persona files + memory.md that compose the system prompt.

    Used to detect file changes mid-session so the cache is invalidated.
    """
    import hashlib

    from codeagent.core.settings import get_system_prompt_filenames
    from seed.core.paths import agent_id_default, agent_persona_dir, agent_persona_memory_path

    aid = (agent_id or "").strip() or agent_id_default()
    persona_dir = agent_persona_dir(aid)
    h = hashlib.sha256()
    for fname in sorted(get_system_prompt_filenames()):
        p = persona_dir / fname
        if p.is_file():
            h.update(p.read_bytes())
    p_mem = agent_persona_memory_path(aid)
    if p_mem.is_file():
        h.update(p_mem.read_bytes())
    return h.hexdigest()


def get_cached_system_prompt(session, *, agent_id: str | None = None) -> str:
    """Return system prompt, building fresh only on first turn or if files changed.

    Caches the result in ``session.metadata["base_system"]`` with a hash
    in ``session.metadata["base_system_hash"]``.
    """
    md = session.metadata
    if not isinstance(md, dict):
        md = {}
    aid = (agent_id or "").strip() or "default"
    current_hash = _compute_persona_hash(aid)
    cached = md.get("base_system", "")
    cached_hash = md.get("base_system_hash", "")

    if cached and cached_hash == current_hash:
        return cached

    fresh = fresh_system_prompt(agent_id=aid)
    if isinstance(session.metadata, dict):
        session.metadata["base_system"] = fresh
        session.metadata["base_system_hash"] = current_hash
    return fresh


def _codeagent_vars_dict(agent_id: str) -> dict[str, str]:
    """CodeAgent-specific variables extending Seed's base vars.

    These are product-level path concepts relative to the CodeAgent
    working directory (``Path.cwd()``), which may differ from Seed's
    ``project_root()`` (``$SEED_PROJECT_ROOT``).
    """
    from seed.core.paths import agent_home
    from pathlib import Path

    root = Path.cwd().resolve()
    return {
        "SESSIONS_ARTIFACTS": str(agent_home(agent_id) / "sessions" / "_artifacts"),
        "PLANS": str(root / ".plans"),
        "SCRIPTS": str(root / ".scripts"),
        "DOCS": str(root / "docs"),
        "TMP": str(root / ".tmp"),
        "SESSION_LOG": str(root / "session-log"),
        "AGENT_STATE": str(root / ".agent-state.md"),
    }


def _codeagent_path_registry(vars_dict: dict[str, str]) -> str:
    """Build the CodeAgent extension of the path registry table."""
    rows: list[str] = [
        "\n\n## 路径基准（CodeAgent 扩展）\n",
        "| 变量 | 当前值 |",
        "|------|--------|",
    ]
    for key in sorted(vars_dict):
        rows.append(f"| `${key}` | `{vars_dict[key]}` |")
    return "\n".join(rows)


def fresh_system_prompt(*, agent_id: str | None = None) -> str:
    """
    System prompt for chat: respects Web UI ``config_md_enabled``, plugin skills
    (via ``build_system_prompt``), and optional persona ``memory.md``.
    """
    explicit = pick_nonempty(*_ea.SYSTEM_PROMPT)
    if explicit.strip():
        return explicit.strip()

    from seed.core.paths import agent_id_default

    aid = (agent_id or "").strip() or agent_id_default()

    from codeagent.core.settings import get_system_prompt_filenames

    base = build_system_prompt(
        base=project_root(),
        filenames=get_system_prompt_filenames(),
        agent_id=aid,
    )

    # Merge Seed vars + CodeAgent vars for memory.md rendering
    from seed.core.config_plane import render_persona, _build_seed_vars_dict

    seed_vars = _build_seed_vars_dict(aid, project_root())
    ca_vars = _codeagent_vars_dict(aid)
    all_vars: dict[str, str] = {**seed_vars, **ca_vars}

    try:
        from seed.core.paths import agent_persona_memory_path

        p = agent_persona_memory_path(aid)
        if p.is_file():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                # Render memory.md through render_persona (expands $VAR in memory content)
                text = render_persona(text, all_vars)
                max_chars = int(pick_nonempty(*_ea.PERSONA_MEMORY_MAX_CHARS) or "4000")
                max_chars = max(200, min(max_chars, 50_000))
                if len(text) > max_chars:
                    text = text[: max_chars - 20].rstrip() + "\n…[已截断]"
                header_path = f"agents/{aid}/persona/memory.md"
                base = (
                    base.rstrip()
                    + "\n\n---\n"
                    + f"## Persona core memory (`{header_path}`)\n\n"
                    + text
                    + "\n"
                )
    except Exception:
        pass

    # Append CodeAgent extension path registry
    base += _codeagent_path_registry(ca_vars)

    base = base.rstrip() + vision_multimodal_appendix()
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
            from codeagent.core.attachments import content_text_for_skills
            from codeagent.skills.select import build_selected_skills_appendix

            appendix = build_selected_skills_appendix(
                agent_id,
                user_text=content_text_for_skills(user_text),
            )
            if appendix:
                parts.append(appendix)
        except Exception:
            pass

    if not parts:
        return None
    return "\n".join(parts)


def vision_multimodal_appendix() -> str:
    from codeagent.core.image_understanding import (
        MCP_QUALIFIED_UNDERSTAND_IMAGE,
        minimax_mcp_configured,
    )
    from codeagent.core.vision_models import list_vision_presets

    mcp = minimax_mcp_configured()
    has_vision = bool(list_vision_presets())
    parts = ["\n\n## Multimodal (images)\n\n"]

    if mcp:
        parts.append(
            "When the user message contains `[attachment:<id> ...]` and you need to **understand** "
            "image content, call `attachment_resolve_path` with the attachment id, then "
            f"`{MCP_QUALIFIED_UNDERSTAND_IMAGE}` with `image_url` set to the returned absolute "
            "`path` and a clear `prompt` describing what to extract. "
            "Do not claim to see images without tool results.\n\n"
        )
    if has_vision:
        parts.append(
            "When `[attachment:...]` or `[image_dir:...]` appears, you may also use "
            "`vision_analyze` or `vision_analyze_directory` (requires an active vision LLM preset). "
            "Prefer the tool that matches your available backends.\n\n"
        )
    elif not mcp:
        parts.append(
            "Image understanding requires a vision LLM preset or MiniMax MCP; "
            "do not guess image content without tools.\n\n"
        )

    parts.append(
        "When the user asks to **create, draw, or generate** an image, call `image_generate` "
        "with a detailed prompt. For image-to-image (keep subject/style from a photo), pass "
        "`attachment_ids` or `reference_image_urls`. Share returned `attachment_id` / URL in your reply.\n\n"
        "When the user asks to **compose, write, or generate music or a song**, call `music_generate` "
        "with a style `prompt` and `lyrics` (use [Verse]/[Chorus] tags). For instrumental-only, "
        "set `is_instrumental=true`. If lyrics are missing, use `lyrics_optimizer=true` or ask the user. "
        "Share the returned `attachment_id` / URL for playback.\n\n"
        "When the user asks to **create or generate a video** (text-to-video, animate an image, or "
        "keyframe transition), call `video_generate` with a detailed cinematic `prompt`. For image-to-video, "
        "pass `attachment_ids` or `image_url`. Share the returned `attachment_id` / URL for playback.\n\n"
        "For **audio** attachments, call `audio_transcribe` before answering about spoken content.\n"
        "For **video** attachments, call `video_analyze` (requires server ffmpeg for frame sampling).\n"
        "Camera captures appear as `[attachment:...]` — analyze them like uploaded photos.\n"
    )
    return "".join(parts)


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
        from codeagent.core.attachments import content_text_for_skills
        from codeagent.memory.diary import append_diary_entry, archive_old_diaries

        u = content_text_for_skills(user_text or "")
        if not u and (user_text or "").strip():
            u = "[用户附加了图片或文档]"
        r = (reply or "").strip()
        block = f"**用户**: {u[:500]}\n\n**助手**: {r[:800]}"
        if tools_used:
            block += f"\n\n**工具**: {', '.join(tools_used[:16])}"
        append_diary_entry(agent_id, text=block, project_id=project_id or None)
        keep = ca_env.pick_int(7, ca_env.DIARY_KEEP_DAYS)
        archive_old_diaries(agent_id, keep_days=max(1, min(keep, 60)))
    except Exception:
        pass
