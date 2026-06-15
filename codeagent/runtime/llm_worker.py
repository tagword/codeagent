"""LLM worker: isolated tool loop per agent_id."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from seed.core.agent_context import set_active_llm_session
from seed.core.agent_runtime import (
    build_api_projection_messages,
    maybe_compact_context_messages,
    merge_llm_tail_into_full,
    persist_compact_summary,
    run_llm_tool_loop,
    strip_ephemeral_message_fields,
)
from seed.core.llm_exec import LLMError
from seed.core.llm_presets import llm_executor_from_resolved, resolve_preset
from seed.core.llm_sess import load_or_create_chat_session, merge_fresh_system, persist_chat_session
from seed.core.mem_bridge import finalize_episodic_for_llm
from codeagent.core import env as ca_env

from codeagent.runtime.prompt_enrichment import build_skills_suffix, fresh_system_prompt, get_cached_system_prompt
from codeagent.tools.agent_tools import get_tools_for_agent


@dataclass
class LLMWorker:
    """Run one user turn with per-agent tools and optional project scope."""

    agent_id: str = "default"
    project_id: str = ""
    max_user_rounds: int = field(
        default_factory=lambda: ca_env.pick_int(12, ca_env.CHAT_USER_ROUNDS)
    )

    def run(
        self,
        *,
        session_id: str,
        user_text: str,
        tools: list[dict[str, Any]] | None = None,
        max_tool_rounds: int = 16,
    ) -> tuple[str, dict[str, Any]]:
        aid = (self.agent_id or "default").strip() or "default"
        sid = (session_id or "worker").strip() or "worker"
        mkey = f"{aid}::{sid}"

        reg, exe = get_tools_for_agent(aid)
        llm = llm_executor_from_resolved(resolve_preset(None))

        chat_sess = load_or_create_chat_session(sid, aid, self.project_id or None)
        fresh_sys = get_cached_system_prompt(chat_sess, agent_id=aid)
        if not chat_sess.messages:
            chat_sess.messages = [{"role": "system", "content": fresh_sys}]
        else:
            chat_sess.messages[:] = merge_fresh_system(chat_sess.messages, fresh_sys)

        chat_sess.messages.append({"role": "user", "content": user_text})
        skills_suffix = build_skills_suffix(aid, user_text=user_text)
        api_msgs = build_api_projection_messages(
            chat_sess.messages,
            max_user_rounds=self.max_user_rounds,
            skills_suffix=skills_suffix,
        )
        compact_result = maybe_compact_context_messages(api_msgs, llm)
        persist_compact_summary(chat_sess.messages, compact_result)
        # ── If compact happened, inject current project state into system message ──
        if compact_result is not None:
            _inject_state_into_system(api_msgs, aid)
        strip_ephemeral_message_fields(api_msgs)
        if not isinstance(chat_sess.metadata, dict):
            chat_sess.metadata = {}
        finalize_episodic_for_llm(
            api_msgs,
            chat_sess.metadata,
            agent_id=aid,
            session_id=sid,
            project_id=self.project_id or None,
            compact_happened=compact_result is not None,
        )

        set_active_llm_session(mkey)
        try:
            n_before = len(api_msgs)
            reply, meta, tools_used, tool_trace, loop_meta = asyncio.run(
                run_llm_tool_loop(
                    llm,
                    exe,
                    messages=api_msgs,
                    registry=reg,
                    max_tool_rounds=max_tool_rounds,
                )
            )
            merge_llm_tail_into_full(chat_sess.messages, api_msgs, n_before)
            persist_chat_session(chat_sess, aid)
            out_meta = dict(meta or {})
            out_meta.update(loop_meta or {})
            out_meta["agent_id"] = aid
            out_meta["tools_used"] = tools_used
            out_meta["tool_trace"] = tool_trace
            return reply or "", out_meta
        except LLMError as e:
            return f"[LLM error] {e}", {"agent_id": aid, "error": str(e)}
        finally:
            set_active_llm_session(None)


# ---------------------------------------------------------------------------
# State injection (compact-time only)
# ---------------------------------------------------------------------------

def _inject_state_into_system(api_msgs: list[dict[str, Any]], agent_id: str) -> None:
    """Read ``.codeagent/{agent_id}/state.md`` and inject into ``api_msgs[0]``.

    Called only when ``maybe_compact_context_messages`` has just truncated
    the context.  Strips any previous ``<<<STATE>>>`` block and inserts
    the current state so the agent can pick up where it left off.
    """
    import re

    try:
        from codeagent.core.paths import read_state_file
    except Exception:
        return

    state_text = read_state_file(agent_id)
    if not state_text:
        return

    sys_msg = api_msgs[0]
    content = str(sys_msg.get("content") or "")

    # Strip any previous state block
    content = re.sub(
        r"\n+<<<STATE>>>\n.*?\n<<<END_STATE>>>\n?",
        "\n",
        content,
        flags=re.DOTALL,
    ).strip()

    state_block = (
        "\n\n<<<STATE>>>\n"
        "## 当前项目状态\n\n"
        f"{state_text}\n"
        "<<<END_STATE>>>"
    )
    sys_msg["content"] = content + state_block
