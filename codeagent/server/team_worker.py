"""Team member worker — real LLM execution for team runs.

Single responsibility: turn one "member task" into real text output.

Design (A 起步 / B 留接口):
- Members are text-producing roles. Each step is a *plain LLM completion*
  (via ``llm.generate``), NOT the full agent tool-loop — team members in the A
  form don't need to run arbitrary tools / MCP, they produce reasoned text for
  a given role. This keeps execution lightweight, fast, and free of the
  tool-loop/MCP machinery that would hang in a detached thread.
- Two member forms:
  - A (role-play, default): member is an agent_id string, or a dict with
    ``role``/``system_prompt``/``model``. A role system prompt is prepended.
  - B (reserved): if a member ever binds a real AutonomousAgent (independent
    memory/tools/model), only the *inside* of :func:`run_member_step` needs to
    change — the engine-facing signature stays identical.

``run_member_step`` is synchronous and pure: it does not touch run/step
persistence (the engine records those) and needs no running event loop (safe to
drive from a background thread).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _member_agent_id(member) -> str:
    """Agent id for a member (str id, or dict with ``id``/``agent_id``/``role``)."""
    if isinstance(member, str):
        return member
    if isinstance(member, dict):
        return str(member.get("id") or member.get("agent_id") or member.get("role") or "")
    return ""


def _member_role_prompt(member) -> str:
    """Optional role/system prompt for a member (A role-play form)."""
    if isinstance(member, dict):
        return str(member.get("system_prompt") or member.get("role_prompt") or "")
    return ""


def _member_model(member) -> str:
    """Optional per-member model override (A/B seam)."""
    if isinstance(member, dict):
        return str(member.get("model") or member.get("llm_id") or "")
    return ""


def run_member_step(
    *,
    agent_id: str,
    task: str,
    role_prompt: str = "",
    llm_id: str = "",
    max_tokens: int | None = None,
    enable_thinking: bool | None = None,
) -> str:
    """Run one real LLM turn for a team member, returning the reply text.

    Uses a plain completion (``llm.generate``) with an optional role system
    prompt — lightweight, no tool loop / MCP, safe off the main event loop.
    """
    from codeagent.core.vision_models import resolve_main_llm

    llm = resolve_main_llm(llm_id or None)

    system = role_prompt or (
        "你是一个团队协作成员。请基于你收到的任务，给出清晰、直接、可用的输出。"
        "不要编造工具调用，不要输出多余的解释性框架。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
    try:
        content, _meta = llm.generate(
            messages,
            max_turns=1,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
        )
    except Exception as exc:  # LLMError 等 —— 交给 engine 记录为该 step 失败
        logger.warning("team member step failed agent=%s: %s", agent_id, exc)
        raise
    return str(content or "").strip()
